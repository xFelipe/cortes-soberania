"""Testes para stages/triage_transcript.py."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from canal_soberania.config import CanaisConfig, Canal, Parametros
from canal_soberania.db import (
    connect,
    get_videos_by_status,
    init_db,
    insert_video,
)
from canal_soberania.llm import LLMResponse
from canal_soberania.models import Video, VideoStatus
from canal_soberania.stages.triage_transcript import (
    _build_transcript_prompt,
    _load_transcript_segments,
    _parse_transcript_response,
    triage_video_transcript,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"
PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts" / "triagem_transcript.txt"
CRITERIOS = Path(__file__).parent.parent / "config" / "criterios_relevancia.md"

_SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 60.0, "text": "Brasil e BRICS: soberania econômica em debate."},
    {"start": 60.0, "end": 120.0, "text": "O pré-sal é um ativo estratégico fundamental."},
    {"start": 120.0, "end": 200.0, "text": "Precisamos de reindustrialização para ser soberanos."},
]


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def transcript_file(tmp_path: Path) -> Path:
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    path = tdir / "dQw4w9WgXcQ.json"
    path.write_text(
        json.dumps({"video_id": "dQw4w9WgXcQ", "language": "pt", "segments": _SAMPLE_SEGMENTS}),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def video(transcript_file: Path) -> Video:
    return Video(
        video_id="dQw4w9WgXcQ",
        canal_id="arte_da_guerra",
        title="Brasil e BRICS",
        published_at="2026-05-10T12:00:00Z",
        duration_s=3600,
        status=VideoStatus.TRANSCRIBED,
        transcript_path=str(transcript_file),
    )


@pytest.fixture
def canais_cfg() -> CanaisConfig:
    canal = Canal(
        id="arte_da_guerra",
        nome="Arte da Guerra",
        handle="@ARTEDAGUERRA",
        channel_url="https://www.youtube.com/@ARTEDAGUERRA",
        tema_primario="geopolitica_defesa",
    )
    return CanaisConfig(canais=[canal], parametros=Parametros())


@pytest.fixture
def prompt_template() -> str:
    return PROMPT_TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture
def criterios() -> str:
    return CRITERIOS.read_text(encoding="utf-8")


def _make_llm(score: int = 8, is_relevant: bool = True) -> MagicMock:
    llm = MagicMock()
    llm.complete.return_value = LLMResponse(
        text=json.dumps({
            "score": score,
            "is_relevant": is_relevant,
            "themes_detected": ["geopolitica_brics", "energia_pre_sal"],
            "trechos_relevantes_aprox": ["00:00-01:00", "01:00-03:20"],
            "profundidade": "alta",
            "tom_editorial_ok": True,
            "rationale": "Foco intenso em soberania e BRICS com dados.",
        }),
        model="claude-sonnet-4-6",
        tokens_in=4000,
        tokens_out=200,
        cost_usd=0.015,
    )
    return llm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_load_transcript_segments(transcript_file: Path) -> None:
    segments = _load_transcript_segments(str(transcript_file))
    assert len(segments) == 3
    assert segments[0]["text"] == "Brasil e BRICS: soberania econômica em debate."


def test_build_transcript_prompt_fills_placeholders(
    prompt_template: str, criterios: str, video: Video
) -> None:
    segments = _load_transcript_segments(video.transcript_path)  # type: ignore[arg-type]
    from canal_soberania.stages.transcribe import format_segments_for_prompt
    transcript_text = format_segments_for_prompt(segments)
    result = _build_transcript_prompt(
        prompt_template, criterios, video, "Arte da Guerra", transcript_text
    )
    assert "BRICS" in result
    assert "60" in result  # 3600s/60
    for ph in ["{criterios_relevancia}", "{canal_nome}", "{title}", "{duracao_min}", "{transcript_segmentos}"]:
        assert ph not in result


def test_parse_transcript_response_valid() -> None:
    raw = json.dumps({
        "score": 8,
        "is_relevant": True,
        "themes_detected": ["geopolitica_brics"],
        "trechos_relevantes_aprox": ["00:00-10:00"],
        "profundidade": "alta",
        "tom_editorial_ok": True,
        "rationale": "Muito relevante",
    })
    result = _parse_transcript_response(raw, "dQw4w9WgXcQ", "claude-sonnet-4-6", 4000, 200, 0.015)
    assert result.score == 8
    assert result.stage == "transcript"
    assert result.is_relevant is True


# ---------------------------------------------------------------------------
# triage_video_transcript integration
# ---------------------------------------------------------------------------


def test_triage_video_transcript_passed(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = _make_llm(score=8, is_relevant=True)
    result = triage_video_transcript(
        video=video, conn=db, llm=llm, model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg, threshold=7,
    )

    assert result is not None
    assert result.is_relevant is True
    assert len(get_videos_by_status(db, VideoStatus.TRIAGE_TRANSCRIPT_PASSED)) == 1


def test_triage_video_transcript_rejected(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = _make_llm(score=5, is_relevant=False)
    result = triage_video_transcript(
        video=video, conn=db, llm=llm, model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg, threshold=7,
    )

    assert result is not None
    assert result.is_relevant is False
    assert len(get_videos_by_status(db, VideoStatus.TRIAGE_TRANSCRIPT_REJECTED)) == 1


def test_triage_video_transcript_dry_run(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = _make_llm()
    result = triage_video_transcript(
        video=video, conn=db, llm=llm, model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg, dry_run=True,
    )

    assert result is None
    llm.complete.assert_not_called()
    assert len(get_videos_by_status(db, VideoStatus.TRANSCRIBED)) == 1


def test_triage_video_transcript_missing_path(
    db: sqlite3.Connection, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    v = Video(
        video_id="dQw4w9WgXcQ",
        canal_id="arte_da_guerra",
        title="Teste",
        published_at="2026-05-10T12:00:00Z",
        status=VideoStatus.TRANSCRIBED,
        transcript_path=None,
    )
    with db:
        insert_video(db, v)

    result = triage_video_transcript(
        video=v, conn=db, llm=_make_llm(), model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg,
    )
    assert result is None


def test_triage_video_transcript_llm_error(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = MagicMock()
    llm.complete.side_effect = RuntimeError("rate limited")

    result = triage_video_transcript(
        video=video, conn=db, llm=llm, model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg,
    )
    assert result is None
    assert len(get_videos_by_status(db, VideoStatus.PROCESSING_ERROR)) == 1


def test_triage_video_transcript_records_cost(
    db: sqlite3.Connection, video: Video, canais_cfg: CanaisConfig,
    prompt_template: str, criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = _make_llm()
    triage_video_transcript(
        video=video, conn=db, llm=llm, model="claude-sonnet-4-6",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg,
    )

    row = db.execute("SELECT cost_usd FROM api_costs WHERE model='claude-sonnet-4-6'").fetchone()
    assert row is not None
    assert row["cost_usd"] == pytest.approx(0.015)
