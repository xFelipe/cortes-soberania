"""Testes para o sistema de eval de prompts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from canal_soberania.config import Settings
from canal_soberania.evals.compare import compare_runs
from canal_soberania.evals.models import EvalEntry, EvalResult, GroundTruth, RunSummary
from canal_soberania.evals.runner import compute_metrics, load_dataset, load_run, run_eval
from canal_soberania.llm import LLMResponse

# ---------------------------------------------------------------------------
# Stub LLM backend
# ---------------------------------------------------------------------------


class StubLLM:
    """Backend determinístico para testes — responde is_relevant e score fixos."""

    def __init__(
        self,
        is_relevant: bool = True,
        score: int = 7,
        raise_error: Exception | None = None,
    ) -> None:
        self.is_relevant = is_relevant
        self.score = score
        self.raise_error = raise_error
        self.call_count = 0

    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        system: str | None = None,
        task: str = "",
    ) -> LLMResponse:
        self.call_count += 1
        if self.raise_error is not None:
            raise self.raise_error
        text = json.dumps(
            {
                "score": self.score,
                "is_relevant": self.is_relevant,
                "themes_detected": ["soberania_nacional"],
                "rationale": "stub",
            }
        )
        return LLMResponse(text=text, model=model, tokens_in=100, tokens_out=50, cost_usd=0.001)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA = Path(__file__).parent.parent / "schema.sql"
_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _settings() -> Settings:
    return Settings(anthropic_api_key="test-key", anthropic_model_triage="claude-haiku-4-5-20251001")


def _make_dataset_file(
    tmp_path: Path,
    entries: list[EvalEntry],
    filename: str = "dataset.jsonl",
) -> Path:
    p = tmp_path / filename
    with p.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(e.model_dump_json() + "\n")
    return p


def _entry(video_id: str, is_relevant: bool) -> EvalEntry:
    assert len(video_id) == 11, f"video_id deve ter 11 chars: {video_id!r}"
    return EvalEntry(
        video_id=video_id,
        title=f"Vídeo {video_id}",
        description="Teste de avaliação do pipeline de triagem.",
        tags=["soberania", "teste"],
        canal_id="UCTest00001",
        ground_truth={"triage_metadata": GroundTruth(is_relevant=is_relevant, score_expected=7 if is_relevant else 2)},
    )


def _make_run_file(tmp_path: Path, results: list[EvalResult], name: str = "run.jsonl") -> tuple[Path, Path]:
    """Escreve um run JSONL + summary JSON em tmp_path. Retorna (jsonl_path, summary_path)."""
    jsonl_path = tmp_path / name
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(r.model_dump_json() + "\n")
    # Cria summary sintético
    metrics = compute_metrics(results)
    summary = RunSummary(
        run_id=jsonl_path.stem,
        stage="triage_metadata",
        backend="anthropic",
        prompt_version="v1",
        precision=metrics["precision"],
        recall=metrics["recall"],
        f1=metrics["f1"],
        accuracy=metrics["accuracy"],
        total_cost_usd=sum(r.cost_usd for r in results),
        total_tokens_in=sum(r.tokens_in for r in results),
        total_tokens_out=sum(r.tokens_out for r in results),
        total_entries=len(results),
        ts="20260521T000000Z",
    )
    summary_path = tmp_path / f"{jsonl_path.stem}.summary.json"
    summary_path.write_text(summary.model_dump_json(), encoding="utf-8")
    return jsonl_path, summary_path


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------


def test_compute_metrics_perfect() -> None:
    results = [
        EvalResult(video_id="x", stage="s", is_relevant_predicted=True, score_predicted=7,
                   is_relevant_expected=True, tokens_in=1, tokens_out=1, cost_usd=0,
                   model_used="m", raw_response="", correct=True),
        EvalResult(video_id="y", stage="s", is_relevant_predicted=False, score_predicted=2,
                   is_relevant_expected=False, tokens_in=1, tokens_out=1, cost_usd=0,
                   model_used="m", raw_response="", correct=True),
    ]
    m = compute_metrics(results)
    assert m["precision"] == pytest.approx(1.0)
    assert m["recall"] == pytest.approx(1.0)
    assert m["accuracy"] == pytest.approx(1.0)


def test_compute_metrics_all_wrong() -> None:
    results = [
        EvalResult(video_id="x", stage="s", is_relevant_predicted=False, score_predicted=2,
                   is_relevant_expected=True, tokens_in=1, tokens_out=1, cost_usd=0,
                   model_used="m", raw_response="", correct=False),
        EvalResult(video_id="y", stage="s", is_relevant_predicted=True, score_predicted=8,
                   is_relevant_expected=False, tokens_in=1, tokens_out=1, cost_usd=0,
                   model_used="m", raw_response="", correct=False),
    ]
    m = compute_metrics(results)
    assert m["precision"] == pytest.approx(0.0)
    assert m["accuracy"] == pytest.approx(0.0)


def test_compute_metrics_empty() -> None:
    m = compute_metrics([])
    assert m["precision"] == pytest.approx(1.0)
    assert m["recall"] == pytest.approx(1.0)
    assert m["accuracy"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# load_dataset
# ---------------------------------------------------------------------------


def test_load_dataset_roundtrip(tmp_path: Path) -> None:
    entries = [_entry(f"abcdefg000{i}", True) for i in range(3)]
    p = _make_dataset_file(tmp_path, entries)
    loaded = load_dataset(p)
    assert len(loaded) == 3
    assert loaded[0].video_id == entries[0].video_id


def test_load_dataset_skips_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "d.jsonl"
    p.write_text(
        _entry("abcdefg0001", True).model_dump_json() + "\n\n"
        + _entry("abcdefg0002", False).model_dump_json() + "\n",
        encoding="utf-8",
    )
    loaded = load_dataset(p)
    assert len(loaded) == 2


# ---------------------------------------------------------------------------
# run_eval
# ---------------------------------------------------------------------------


def test_run_eval_metadata_correct_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub sempre retorna is_relevant=True; dataset tem 3 entradas todas True → métricas perfeitas."""
    entries = [_entry(f"testid{i:05d}", True) for i in range(1, 4)]
    dataset_path = _make_dataset_file(tmp_path, entries)

    stub = StubLLM(is_relevant=True, score=7)
    monkeypatch.setattr("canal_soberania.evals.runner._load_backend", lambda *_args, **_kw: stub)

    summary = run_eval(
        stage="triage_metadata",
        backend_name="anthropic",
        prompt_version="v1",
        dataset_path=dataset_path,
        output_dir=tmp_path / "runs",
        settings=_settings(),
    )

    assert summary.total_entries == 3
    assert summary.precision == pytest.approx(1.0)
    assert summary.recall == pytest.approx(1.0)
    assert summary.f1 == pytest.approx(1.0)
    assert summary.accuracy == pytest.approx(1.0)
    assert summary.total_cost_usd == pytest.approx(3 * 0.001)


def test_run_eval_metadata_false_positive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub retorna sempre True; 1 entrada é False → precision < 1.0."""
    entries = [
        _entry("testid00001", True),
        _entry("testid00002", False),  # ground truth False, stub says True → FP
    ]
    dataset_path = _make_dataset_file(tmp_path, entries)
    monkeypatch.setattr(
        "canal_soberania.evals.runner._load_backend",
        lambda *_a, **_kw: StubLLM(is_relevant=True),
    )
    summary = run_eval(
        stage="triage_metadata",
        backend_name="anthropic",
        prompt_version="v1",
        dataset_path=dataset_path,
        output_dir=tmp_path / "runs",
        settings=_settings(),
    )
    assert summary.precision < 1.0  # FP exists
    assert summary.accuracy < 1.0


def test_run_eval_writes_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run_eval deve criar arquivo JSONL com 1 linha por entrada."""
    entries = [_entry(f"writeid{i:04d}", True) for i in range(1, 4)]
    dataset_path = _make_dataset_file(tmp_path, entries)
    monkeypatch.setattr(
        "canal_soberania.evals.runner._load_backend",
        lambda *_a, **_kw: StubLLM(),
    )
    runs_dir = tmp_path / "runs"
    summary = run_eval(
        stage="triage_metadata",
        backend_name="anthropic",
        prompt_version="v1",
        dataset_path=dataset_path,
        output_dir=runs_dir,
        settings=_settings(),
    )
    jsonl_path = runs_dir / f"{summary.run_id}.jsonl"
    assert jsonl_path.exists()
    lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 3
    # Each line is valid JSON with video_id
    for line in lines:
        data = json.loads(line)
        assert "video_id" in data
        assert "correct" in data


def test_run_eval_backend_error_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Quando o LLM lança exceção, a entrada é marcada com error=True e o runner continua."""
    entries = [_entry(f"errid{i:06d}", True) for i in range(3)]
    dataset_path = _make_dataset_file(tmp_path, entries)
    monkeypatch.setattr(
        "canal_soberania.evals.runner._load_backend",
        lambda *_a, **_kw: StubLLM(raise_error=RuntimeError("Conexão recusada")),
    )
    summary = run_eval(
        stage="triage_metadata",
        backend_name="anthropic",
        prompt_version="v1",
        dataset_path=dataset_path,
        output_dir=tmp_path / "runs",
        settings=_settings(),
    )
    # Todas as entradas processadas (mesmo com erro)
    assert summary.total_entries == 3
    # Erros levam a is_relevant_predicted=False → nenhum TP ou FP corretos
    jsonl_path = tmp_path / "runs" / f"{summary.run_id}.jsonl"
    lines = jsonl_path.read_text().splitlines()
    for line in lines:
        data = json.loads(line)
        assert data["error"] is not None


def test_run_eval_unknown_stage_raises(tmp_path: Path) -> None:
    entries = [_entry("unknwstage1", True)]
    dataset_path = _make_dataset_file(tmp_path, entries)
    with pytest.raises(ValueError, match="Stage desconhecido"):
        run_eval(
            stage="triage_nonexistent",
            backend_name="anthropic",
            prompt_version="v1",
            dataset_path=dataset_path,
            output_dir=tmp_path / "runs",
            settings=_settings(),
        )


def test_run_eval_no_entries_for_stage_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dataset sem entries para o stage solicitado deve levantar ValueError."""
    # Entry só tem triage_caption, não triage_transcript
    entries = [
        EvalEntry(
            video_id="notranscpt",
            title="T",
            description="D",
            tags=[],
            canal_id="UC0",
            ground_truth={"triage_caption": GroundTruth(is_relevant=True)},
        )
    ]
    dataset_path = _make_dataset_file(tmp_path, entries)
    monkeypatch.setattr(
        "canal_soberania.evals.runner._load_backend",
        lambda *_a, **_kw: StubLLM(),
    )
    with pytest.raises(ValueError, match="Nenhuma entrada"):
        run_eval(
            stage="triage_transcript",
            backend_name="anthropic",
            prompt_version="v1",
            dataset_path=dataset_path,
            output_dir=tmp_path / "runs",
            settings=_settings(),
        )


# ---------------------------------------------------------------------------
# load_run
# ---------------------------------------------------------------------------


def test_load_run_reads_summary(tmp_path: Path) -> None:
    results = [
        EvalResult(video_id="abcdefg0001", stage="triage_metadata", is_relevant_predicted=True,
                   score_predicted=7, is_relevant_expected=True, tokens_in=100, tokens_out=50,
                   cost_usd=0.001, model_used="claude-haiku", raw_response="{}", correct=True),
    ]
    jsonl_path, _ = _make_run_file(tmp_path, results, "my_run.jsonl")
    summary, loaded = load_run(jsonl_path)
    assert len(loaded) == 1
    assert summary.total_entries == 1
    assert summary.precision == pytest.approx(1.0)


def test_load_run_no_summary_recalculates(tmp_path: Path) -> None:
    """Sem .summary.json, load_run deve calcular métricas do zero."""
    jsonl_path = tmp_path / "orphan_run.jsonl"
    result = EvalResult(
        video_id="abcdefg0001", stage="triage_metadata", is_relevant_predicted=False,
        score_predicted=2, is_relevant_expected=True, tokens_in=1, tokens_out=1,
        cost_usd=0, model_used="m", raw_response="", correct=False,
    )
    jsonl_path.write_text(result.model_dump_json() + "\n", encoding="utf-8")
    summary, loaded = load_run(jsonl_path)
    assert len(loaded) == 1
    assert summary.recall == pytest.approx(0.0)  # FN=1, TP=0


# ---------------------------------------------------------------------------
# compare_runs / HTML
# ---------------------------------------------------------------------------


def _make_eval_result(video_id: str, predicted: bool, expected: bool) -> EvalResult:
    return EvalResult(
        video_id=video_id,
        stage="triage_metadata",
        is_relevant_predicted=predicted,
        score_predicted=7 if predicted else 2,
        is_relevant_expected=expected,
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.001,
        model_used="claude-haiku",
        raw_response=json.dumps({"score": 7 if predicted else 2, "is_relevant": predicted}),
        correct=predicted == expected,
    )


def test_compare_generates_html(tmp_path: Path) -> None:
    results1 = [
        _make_eval_result("abcdefg0001", True, True),
        _make_eval_result("abcdefg0002", False, False),
        _make_eval_result("abcdefg0003", True, False),   # diverge com run2
    ]
    results2 = [
        _make_eval_result("abcdefg0001", True, True),
        _make_eval_result("abcdefg0002", False, False),
        _make_eval_result("abcdefg0003", False, False),  # diverge com run1
    ]
    run1_path, _ = _make_run_file(tmp_path, results1, "run1.jsonl")
    run2_path, _ = _make_run_file(tmp_path, results2, "run2.jsonl")
    output = tmp_path / "report.html"

    compare_runs(run1_path, run2_path, output)

    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "<html" in html.lower()
    assert "Precision" in html
    assert "abcdefg0001" in html
    assert "abcdefg0003" in html  # linha de divergência deve aparecer


def test_compare_html_no_divergences(tmp_path: Path) -> None:
    """Quando os runs são idênticos, tabela deve ter linhas mas sem diverge."""
    results = [_make_eval_result("abcdefg0001", True, True)]
    run1, _ = _make_run_file(tmp_path, results, "r1.jsonl")
    run2, _ = _make_run_file(tmp_path, results, "r2.jsonl")
    output = tmp_path / "same.html"
    compare_runs(run1, run2, output)
    html = output.read_text()
    assert "<html" in html.lower()
    assert 'class="diverge"' not in html  # sem linhas highlighted de divergência


# ---------------------------------------------------------------------------
# build_dataset
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    """Cria um canal.db mínimo com alguns vídeos e triage_results."""
    db_path = tmp_path / "canal.db"
    schema = Path(__file__).parent.parent / "schema.sql"
    conn = sqlite3.connect(db_path)
    conn.executescript(schema.read_text())
    # Aplica migrations
    migrations_dir = Path(__file__).parent.parent / "migrations"
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        try:
            conn.executescript(sql_file.read_text())
        except Exception:  # noqa: BLE001
            pass

    for i in range(5):
        vid = f"testbuild{i:02d}"
        conn.execute(
            """INSERT INTO videos (video_id, canal_id, title, description, tags,
                published_at, status)
               VALUES (?, 'UCTest00001', ?, 'desc', '[]', '2024-01-01', 'discovered')""",
            (vid, f"Vídeo {i}"),
        )
        conn.execute(
            """INSERT INTO triage_results (video_id, stage, score, is_relevant,
                themes_detected, rationale, raw_response, model_used,
                tokens_in, tokens_out, cost_usd, created_at)
               VALUES (?, 'metadata', ?, ?, '[]', '', '', 'test', 10, 5, 0.001, '2024-01-01')""",
            (vid, 7 if i % 2 == 0 else 3, 1 if i % 2 == 0 else 0),
        )
    conn.commit()
    conn.close()
    return db_path


def test_build_dataset_extracts_videos(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    output = tmp_path / "out.jsonl"

    from canal_soberania.evals.build_dataset import build_dataset

    n = build_dataset(db_path=db_path, limit=10, output_path=output)
    assert n == 5
    assert output.exists()
    lines = [l for l in output.read_text().splitlines() if l.strip()]
    assert len(lines) == 5
    for line in lines:
        data = json.loads(line)
        assert "video_id" in data
        assert "ground_truth" in data
        assert "triage_metadata" in data["ground_truth"]


def test_build_dataset_missing_db(tmp_path: Path) -> None:
    output = tmp_path / "out.jsonl"
    from canal_soberania.evals.build_dataset import build_dataset

    n = build_dataset(db_path=tmp_path / "nonexistent.db", limit=10, output_path=output)
    assert n == 0
    assert not output.exists()


def test_build_dataset_respects_limit(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    output = tmp_path / "out.jsonl"
    from canal_soberania.evals.build_dataset import build_dataset

    n = build_dataset(db_path=db_path, limit=2, output_path=output)
    assert n <= 2
