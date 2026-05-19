"""Testes para stages/triage_metadata.py (LLM e YouTube API mockados)."""

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
from canal_soberania.stages.triage_metadata import (
    _build_prompt,
    _fetch_top_comments,
    _parse_triage_response,
    triage_video_metadata,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"
PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts" / "triagem_metadata.txt"
CRITERIOS = Path(__file__).parent.parent / "config" / "criterios_relevancia.md"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def video() -> Video:
    return Video(
        video_id="dQw4w9WgXcQ",
        canal_id="arte_da_guerra",
        title="Brasil e BRICS: soberania ou alinhamento automático?",
        description="Análise aprofundada da posição do Brasil no BRICS e implicações para soberania.",
        tags=["brics", "geopolitica", "soberania", "brasil"],
        published_at="2026-05-10T12:00:00Z",
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


def _make_llm(score: int = 7, is_relevant: bool = True) -> MagicMock:
    llm = MagicMock()
    response_json = json.dumps({
        "score": score,
        "is_relevant": is_relevant,
        "themes_detected": ["geopolitica_brics", "politica_externa"],
        "rationale": "Foco direto em BRICS e soberania",
    })
    llm.complete.return_value = LLMResponse(
        text=response_json,
        model="claude-haiku-4-5-20251001",
        tokens_in=800,
        tokens_out=100,
        cost_usd=0.0009,
    )
    return llm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_fetch_top_comments_returns_empty_on_error() -> None:
    yt = MagicMock()
    yt.commentThreads.return_value.list.return_value.execute.side_effect = Exception("disabled")
    comments = _fetch_top_comments(yt, "dQw4w9WgXcQ")
    assert comments == []


def test_fetch_top_comments_parses_items() -> None:
    yt = MagicMock()
    yt.commentThreads.return_value.list.return_value.execute.return_value = {
        "items": [
            {"snippet": {"topLevelComment": {"snippet": {"textDisplay": "Ótima análise!"}}}},
            {"snippet": {"topLevelComment": {"snippet": {"textDisplay": "Muito relevante."}}}},
        ]
    }
    comments = _fetch_top_comments(yt, "dQw4w9WgXcQ")
    assert comments == ["Ótima análise!", "Muito relevante."]


def test_build_prompt_fills_all_placeholders(
    prompt_template: str, criterios: str, video: Video
) -> None:
    result = _build_prompt(
        prompt_template, criterios, video, "Arte da Guerra", "geopolitica_defesa", ["comentário 1"]
    )
    assert video.title in result
    assert "BRICS" in result
    assert "comentário 1" in result
    assert "{criterios_relevancia}" not in result
    assert "{title}" not in result


def test_build_prompt_handles_no_comments(
    prompt_template: str, criterios: str, video: Video
) -> None:
    result = _build_prompt(prompt_template, criterios, video, "Arte da Guerra", "geo", [])
    assert "sem comentários" in result


def test_parse_triage_response_valid() -> None:
    raw = json.dumps({
        "score": 8,
        "is_relevant": True,
        "themes_detected": ["geopolitica_brics"],
        "rationale": "Foco em BRICS",
    })
    result = _parse_triage_response(raw, "dQw4w9WgXcQ", "claude-haiku-4-5-20251001", 800, 100, 0.001)
    assert result.score == 8
    assert result.is_relevant is True
    assert "geopolitica_brics" in result.themes_detected
    assert result.stage == "metadata"


def test_parse_triage_response_json_in_markdown_block() -> None:
    raw = '```json\n{"score": 6, "is_relevant": true, "themes_detected": [], "rationale": "ok"}\n```'
    result = _parse_triage_response(raw, "vid12345678", "claude-haiku-4-5-20251001", 100, 50, 0.0)
    assert result.score == 6


# ---------------------------------------------------------------------------
# triage_video_metadata integration
# ---------------------------------------------------------------------------


def test_triage_video_metadata_passed(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = _make_llm(score=7, is_relevant=True)
    result = triage_video_metadata(
        video=video,
        conn=db,
        llm=llm,
        model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template,
        criterios=criterios,
        canais_cfg=canais_cfg,
        threshold=5,
    )

    assert result is not None
    assert result.score == 7
    assert result.is_relevant is True

    passed = get_videos_by_status(db, VideoStatus.TRIAGE_METADATA_PASSED)
    assert len(passed) == 1
    assert passed[0].video_id == "dQw4w9WgXcQ"


def test_triage_video_metadata_rejected(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = _make_llm(score=3, is_relevant=False)
    result = triage_video_metadata(
        video=video,
        conn=db,
        llm=llm,
        model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template,
        criterios=criterios,
        canais_cfg=canais_cfg,
        threshold=5,
    )

    assert result is not None
    assert result.score == 3
    assert result.is_relevant is False

    rejected = get_videos_by_status(db, VideoStatus.TRIAGE_METADATA_REJECTED)
    assert len(rejected) == 1


def test_triage_video_metadata_dry_run_no_db_changes(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = _make_llm(score=8)
    result = triage_video_metadata(
        video=video,
        conn=db,
        llm=llm,
        model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template,
        criterios=criterios,
        canais_cfg=canais_cfg,
        dry_run=True,
    )

    assert result is None
    llm.complete.assert_not_called()
    # vídeo deve continuar em 'discovered'
    assert len(get_videos_by_status(db, VideoStatus.DISCOVERED)) == 1


def test_triage_video_metadata_llm_error_sets_processing_error(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = MagicMock()
    llm.complete.side_effect = RuntimeError("API down")

    result = triage_video_metadata(
        video=video,
        conn=db,
        llm=llm,
        model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template,
        criterios=criterios,
        canais_cfg=canais_cfg,
    )

    assert result is None
    error_videos = get_videos_by_status(db, VideoStatus.PROCESSING_ERROR)
    assert len(error_videos) == 1


def test_triage_video_metadata_records_api_cost(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    llm = _make_llm(score=7)
    triage_video_metadata(
        video=video,
        conn=db,
        llm=llm,
        model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template,
        criterios=criterios,
        canais_cfg=canais_cfg,
    )

    row = db.execute(
        "SELECT cost_usd, tokens_in FROM api_costs WHERE provider='anthropic'"
    ).fetchone()
    assert row is not None
    assert row["cost_usd"] == pytest.approx(0.0009)
    assert row["tokens_in"] == 800


def test_triage_video_metadata_uses_comments_when_youtube_available(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
) -> None:
    with db:
        insert_video(db, video)

    yt = MagicMock()
    yt.commentThreads.return_value.list.return_value.execute.return_value = {
        "items": [
            {"snippet": {"topLevelComment": {"snippet": {"textDisplay": "BRICS é o futuro"}}}}
        ]
    }

    llm = _make_llm(score=8)
    triage_video_metadata(
        video=video,
        conn=db,
        llm=llm,
        model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template,
        criterios=criterios,
        canais_cfg=canais_cfg,
        youtube=yt,
    )

    call_args = llm.complete.call_args
    prompt_sent = call_args[0][0]
    assert "BRICS é o futuro" in prompt_sent
