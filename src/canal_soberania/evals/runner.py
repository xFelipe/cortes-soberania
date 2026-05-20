"""Engine de eval: roda um stage de triagem contra o dataset e mede métricas."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from canal_soberania.config import Canal, CanaisConfig, Parametros, Settings, load_settings
from canal_soberania.db import insert_video
from canal_soberania.evals.models import EvalEntry, EvalResult, GroundTruth, RunSummary
from canal_soberania.llm_backends import AnthropicBackend, OllamaBackend
from canal_soberania.llm_backends.base import LLMBackend
from canal_soberania.models import Video, VideoStatus

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_SCHEMA = _REPO_ROOT / "schema.sql"
_MIGRATIONS_DIR = _REPO_ROOT / "migrations"
_CRITERIOS_PATH = _REPO_ROOT / "config" / "criterios_relevancia.md"
_PROMPTS_DIR = _REPO_ROOT / "prompts"

_STAGE_PROMPT_FILE = {
    "triage_metadata": "triagem_metadata",
    "triage_caption": "triagem_caption",
    "triage_transcript": "triagem_transcript",
}

_STAGE_STATUS_SEED = {
    "triage_metadata": VideoStatus.DISCOVERED,
    "triage_caption": VideoStatus.TRIAGE_METADATA_PASSED,
    "triage_transcript": VideoStatus.TRIAGE_CAPTION_PASSED,
}


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA.read_text())
    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        try:
            conn.executescript(sql_file.read_text())
        except Exception:  # noqa: BLE001
            pass
    return conn


def _load_backend(backend_name: str, settings: Settings) -> LLMBackend:
    if backend_name == "anthropic":
        return AnthropicBackend(
            anthropic_api_key=settings.anthropic_api_key,
            openrouter_api_key=settings.openrouter_api_key,
        )
    if backend_name == "ollama-14b":
        return OllamaBackend(
            model=settings.ollama_model_triage,
            base_url=settings.ollama_base_url,
        )
    if backend_name == "ollama-32b":
        return OllamaBackend(
            model=settings.ollama_model_deep,
            base_url=settings.ollama_base_url,
        )
    if backend_name == "hybrid":
        from canal_soberania.llm_backends import get_llm_backend

        return get_llm_backend(settings.model_copy(update={"llm_backend": "hybrid"}))
    raise ValueError(f"Backend desconhecido: {backend_name!r}. Use: anthropic|ollama-14b|ollama-32b|hybrid")


def _load_prompt(stage: str, version: str) -> str:
    base = _STAGE_PROMPT_FILE.get(stage)
    if base is None:
        raise ValueError(f"Stage desconhecido: {stage!r}")
    if version == "v1":
        path = _PROMPTS_DIR / f"{base}.txt"
    else:
        path = _PROMPTS_DIR / f"{base}_{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8")


def _load_criterios() -> str:
    if _CRITERIOS_PATH.exists():
        return _CRITERIOS_PATH.read_text(encoding="utf-8")
    return ""


def _minimal_canais_cfg(canal_id: str) -> CanaisConfig:
    return CanaisConfig(
        canais=[
            Canal(
                id=canal_id,
                nome=canal_id,
                handle=f"@{canal_id}",
                channel_url=f"https://www.youtube.com/channel/{canal_id}",
                tema_primario="soberania nacional",
            )
        ],
        parametros=Parametros(),
    )


def _make_video(entry: EvalEntry, status: VideoStatus) -> Video:
    return Video(
        video_id=entry.video_id,
        canal_id=entry.canal_id,
        title=entry.title,
        description=entry.description,
        tags=entry.tags,
        published_at="2024-01-01T00:00:00",
        transcript_path=entry.transcript_path,
        status=status,
    )


def _error_result(
    video_id: str, stage: str, gt: GroundTruth, model: str, error: str
) -> EvalResult:
    return EvalResult(
        video_id=video_id,
        stage=stage,
        is_relevant_predicted=False,
        score_predicted=0,
        is_relevant_expected=gt.is_relevant,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        model_used=model,
        raw_response="",
        correct=False,
        error=error,
    )


def _eval_metadata(
    entry: EvalEntry,
    gt: GroundTruth,
    llm: LLMBackend,
    model: str,
    prompt_template: str,
    criterios: str,
) -> EvalResult:
    from canal_soberania.stages.triage_metadata import triage_video_metadata

    conn = _make_conn()
    video = _make_video(entry, VideoStatus.DISCOVERED)
    with conn:
        insert_video(conn, video)

    error: str | None = None
    result = None
    try:
        result = triage_video_metadata(
            video=video,
            conn=conn,
            llm=llm,
            model=model,
            prompt_template=prompt_template,
            criterios=criterios,
            canais_cfg=_minimal_canais_cfg(entry.canal_id),
            youtube=None,
            threshold=5,
        )
    except Exception as exc:
        error = str(exc)
    finally:
        conn.close()

    if error is not None or result is None:
        return _error_result(entry.video_id, "triage_metadata", gt, model, error or "stage retornou None")

    return EvalResult(
        video_id=entry.video_id,
        stage="triage_metadata",
        is_relevant_predicted=result.is_relevant,
        score_predicted=result.score,
        is_relevant_expected=gt.is_relevant,
        tokens_in=result.tokens_in or 0,
        tokens_out=result.tokens_out or 0,
        cost_usd=result.cost_usd or 0.0,
        model_used=result.model_used,
        raw_response=result.raw_response,
        correct=result.is_relevant == gt.is_relevant,
    )


def _eval_caption(
    entry: EvalEntry,
    gt: GroundTruth,
    llm: LLMBackend,
    model: str,
    prompt_template: str,
    criterios: str,
) -> EvalResult:
    from canal_soberania.stages.triage_caption import triage_video_caption

    if not entry.captions:
        return _error_result(entry.video_id, "triage_caption", gt, model, "sem captions no dataset")

    conn = _make_conn()
    video = _make_video(entry, VideoStatus.TRIAGE_METADATA_PASSED)
    with conn:
        insert_video(conn, video)

    error: str | None = None
    result = None
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            captions_dir = Path(tmp_dir)
            vtt_path = captions_dir / f"{entry.video_id}.pt.vtt"
            vtt_path.write_text(f"WEBVTT\n\n{entry.captions}\n", encoding="utf-8")
            result = triage_video_caption(
                video=video,
                conn=conn,
                llm=llm,
                model=model,
                prompt_template=prompt_template,
                criterios=criterios,
                canais_cfg=_minimal_canais_cfg(entry.canal_id),
                captions_dir=captions_dir,
                threshold=6,
            )
    except Exception as exc:
        error = str(exc)
    finally:
        conn.close()

    if error is not None or result is None:
        return _error_result(entry.video_id, "triage_caption", gt, model, error or "stage retornou None")

    return EvalResult(
        video_id=entry.video_id,
        stage="triage_caption",
        is_relevant_predicted=result.is_relevant,
        score_predicted=result.score,
        is_relevant_expected=gt.is_relevant,
        tokens_in=result.tokens_in or 0,
        tokens_out=result.tokens_out or 0,
        cost_usd=result.cost_usd or 0.0,
        model_used=result.model_used,
        raw_response=result.raw_response,
        correct=result.is_relevant == gt.is_relevant,
    )


def _eval_transcript(
    entry: EvalEntry,
    gt: GroundTruth,
    llm: LLMBackend,
    model: str,
    prompt_template: str,
    criterios: str,
) -> EvalResult:
    from canal_soberania.stages.triage_transcript import triage_video_transcript

    if not entry.transcript_path:
        return _error_result(entry.video_id, "triage_transcript", gt, model, "sem transcript_path")
    if not Path(entry.transcript_path).exists():
        return _error_result(
            entry.video_id, "triage_transcript", gt, model,
            f"arquivo não encontrado: {entry.transcript_path}",
        )

    conn = _make_conn()
    video = _make_video(entry, VideoStatus.TRIAGE_CAPTION_PASSED)
    with conn:
        insert_video(conn, video)

    error: str | None = None
    result = None
    try:
        result = triage_video_transcript(
            video=video,
            conn=conn,
            llm=llm,
            model=model,
            prompt_template=prompt_template,
            criterios=criterios,
            canais_cfg=_minimal_canais_cfg(entry.canal_id),
            threshold=7,
        )
    except Exception as exc:
        error = str(exc)
    finally:
        conn.close()

    if error is not None or result is None:
        return _error_result(entry.video_id, "triage_transcript", gt, model, error or "stage retornou None")

    return EvalResult(
        video_id=entry.video_id,
        stage="triage_transcript",
        is_relevant_predicted=result.is_relevant,
        score_predicted=result.score,
        is_relevant_expected=gt.is_relevant,
        tokens_in=result.tokens_in or 0,
        tokens_out=result.tokens_out or 0,
        cost_usd=result.cost_usd or 0.0,
        model_used=result.model_used,
        raw_response=result.raw_response,
        correct=result.is_relevant == gt.is_relevant,
    )


_STAGE_EVAL_FN = {
    "triage_metadata": _eval_metadata,
    "triage_caption": _eval_caption,
    "triage_transcript": _eval_transcript,
}

_STAGE_MODEL_KEY = {
    "triage_metadata": "triage",
    "triage_caption": "triage",
    "triage_transcript": "deep",
}


def compute_metrics(entries: list[EvalResult]) -> dict[str, float]:
    tp = sum(1 for e in entries if e.is_relevant_predicted and e.is_relevant_expected)
    fp = sum(1 for e in entries if e.is_relevant_predicted and not e.is_relevant_expected)
    fn = sum(1 for e in entries if not e.is_relevant_predicted and e.is_relevant_expected)
    tn = sum(1 for e in entries if not e.is_relevant_predicted and not e.is_relevant_expected)
    total = len(entries)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / total if total > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy}


def load_dataset(path: Path) -> list[EvalEntry]:
    entries: list[EvalEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(EvalEntry.model_validate_json(line))
    return entries


def run_eval(
    stage: str,
    backend_name: str,
    prompt_version: str,
    dataset_path: Path,
    output_dir: Path,
    settings: Settings | None = None,
) -> RunSummary:
    """Roda um eval de um stage contra todo o dataset. Persiste resultados em JSONL."""
    if settings is None:
        settings = load_settings()

    eval_fn = _STAGE_EVAL_FN.get(stage)
    if eval_fn is None:
        raise ValueError(f"Stage desconhecido: {stage!r}")

    model_key = _STAGE_MODEL_KEY[stage]
    model = settings.anthropic_model_triage if model_key == "triage" else settings.anthropic_model_deep
    llm = _load_backend(backend_name, settings)
    prompt_template = _load_prompt(stage, prompt_version)
    criterios = _load_criterios()
    dataset = load_dataset(dataset_path)

    filtered = [e for e in dataset if stage in e.ground_truth]
    if not filtered:
        raise ValueError(f"Nenhuma entrada com ground_truth para stage={stage!r}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{ts}_{stage}_{backend_name}_v{prompt_version}"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run_id}.jsonl"

    results: list[EvalResult] = []
    with output_path.open("w", encoding="utf-8") as fh:
        for entry in filtered:
            gt = entry.ground_truth[stage]
            result = eval_fn(entry, gt, llm, model, prompt_template, criterios)
            results.append(result)
            fh.write(result.model_dump_json() + "\n")
            fh.flush()

    metrics = compute_metrics(results)
    summary = RunSummary(
        run_id=run_id,
        stage=stage,
        backend=backend_name,
        prompt_version=prompt_version,
        precision=metrics["precision"],
        recall=metrics["recall"],
        f1=metrics["f1"],
        accuracy=metrics["accuracy"],
        total_cost_usd=sum(r.cost_usd for r in results),
        total_tokens_in=sum(r.tokens_in for r in results),
        total_tokens_out=sum(r.tokens_out for r in results),
        total_entries=len(results),
        ts=ts,
    )

    summary_path = output_dir / f"{run_id}.summary.json"
    summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")

    return summary


def load_run(path: Path) -> tuple[RunSummary, list[EvalResult]]:
    """Lê um arquivo de run JSONL + summary JSON. Recalcula summary se .summary.json ausente."""
    results: list[EvalResult] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            results.append(EvalResult.model_validate_json(line))

    summary_path = path.with_suffix(".summary.json").with_name(path.stem + ".summary.json")
    if summary_path.exists():
        summary = RunSummary.model_validate_json(summary_path.read_text())
    else:
        metrics = compute_metrics(results)
        fname = path.stem
        summary = RunSummary(
            run_id=fname,
            stage="unknown",
            backend="unknown",
            prompt_version="v1",
            precision=metrics["precision"],
            recall=metrics["recall"],
            f1=metrics["f1"],
            accuracy=metrics["accuracy"],
            total_cost_usd=sum(r.cost_usd for r in results),
            total_tokens_in=sum(r.tokens_in for r in results),
            total_tokens_out=sum(r.tokens_out for r in results),
            total_entries=len(results),
            ts="",
        )

    return summary, results
