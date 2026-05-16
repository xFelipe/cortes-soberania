"""Testes para stages/metadata.py (LLM mockado)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, Video
from canal_soberania.stages.metadata import (
    _build_metadata_prompt,
    _load_clip_transcript,
    generate_metadata_for_clip,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"

_SAMPLE_PROMPT_TEMPLATE = (
    "Canal: {canal_fonte_nome} ({canal_fonte_handle})\n"
    "URL: {video_url}\n"
    "Título: {video_title}\n"
    "Duração: {duracao_s}s\n"
    "Hook: {hook}\n"
    "Payoff: {payoff}\n"
    "Tema: {tema_soberania}\n"
    "Transcrição: {clip_transcript}\n"
)

_GOOD_RESPONSE = json.dumps(
    {
        "title": "Brasil perde soberania industrial",
        "description": "Análise sobre desindustrialização.\n\nInscreva-se!\n\n📺 https://youtu.be/abc\n🎙️ @canal\n#soberanianacional",
        "tags": [
            "soberania nacional",
            "brasil",
            "industria",
            "geopolitica",
            "desindustrializacao",
            "politica industrial",
            "economia",
            "defesa",
            "brasil soberano",
            "cortes",
            "podcast",
            "analise",
            "video",
            "short",
            "conteudo",
        ],
    }
)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def video() -> Video:
    return Video(
        video_id="abc123XYZ01",
        canal_id="flow_podcast",
        title="Podcast soberania ep 1",
        published_at="2026-01-01T00:00:00Z",
        duration_s=3600,
    )


@pytest.fixture
def clip() -> Clip:
    return Clip(
        clip_id="abc123XYZ01_30_90",
        video_id="abc123XYZ01",
        start_s=30.0,
        end_s=90.0,
        hook="Brasil perde soberania industrial",
        payoff="precisamos de política industrial",
        tema_soberania="industria_defesa",
        score_viral=8,
        score_relevancia=9,
    )


@pytest.fixture
def video_and_clip_in_db(db: sqlite3.Connection, video: Video, clip: Clip) -> tuple[Video, Clip]:
    insert_video(db, video)
    insert_clip(db, clip)
    return video, clip


@pytest.fixture
def transcript_file(tmp_path: Path, clip: Clip) -> Path:
    p = tmp_path / "transcripts" / f"{clip.video_id}.json"
    p.parent.mkdir()
    segments = [
        {"start": 20.0, "end": 40.0, "text": "Brasil perde soberania industrial."},
        {"start": 40.0, "end": 70.0, "text": "Precisamos de política industrial forte."},
        {"start": 70.0, "end": 100.0, "text": "O pré-sal é estratégico."},
        {"start": 100.0, "end": 200.0, "text": "Este trecho não entra no clipe."},
    ]
    p.write_text(
        json.dumps({"video_id": clip.video_id, "language": "pt", "segments": segments}),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def mock_llm() -> MagicMock:
    from canal_soberania.llm import LLMResponse

    llm = MagicMock()
    llm.complete.return_value = LLMResponse(
        text=_GOOD_RESPONSE,
        model="claude-sonnet-4-6",
        tokens_in=500,
        tokens_out=200,
        cost_usd=0.001,
    )
    return llm


@pytest.fixture
def mock_canais_cfg() -> MagicMock:
    canal = MagicMock()
    canal.id = "flow_podcast"
    canal.nome = "Flow Podcast"
    canal.handle = "@FlowPodcast"
    cfg = MagicMock()
    cfg.canais = [canal]
    return cfg


# ---------------------------------------------------------------------------
# _load_clip_transcript
# ---------------------------------------------------------------------------


def test_load_clip_transcript_filters_by_time(
    db: sqlite3.Connection,
    video_and_clip_in_db: tuple[Video, Clip],
    clip: Clip,
    transcript_file: Path,
    tmp_path: Path,
) -> None:
    db.execute(
        "UPDATE videos SET transcript_path = ? WHERE video_id = ?",
        (str(transcript_file), clip.video_id),
    )
    db.commit()

    result = _load_clip_transcript(clip, db, tmp_path / "transcripts")
    assert "Brasil perde soberania" in result
    assert "política industrial" in result
    # Segment starting at 100s (after clip end=90) should not appear
    assert "Este trecho não entra" not in result


def test_load_clip_transcript_no_transcript(
    db: sqlite3.Connection,
    video_and_clip_in_db: tuple[Video, Clip],
    clip: Clip,
    tmp_path: Path,
) -> None:
    result = _load_clip_transcript(clip, db, tmp_path / "transcripts")
    assert result == ""


def test_load_clip_transcript_missing_file(
    db: sqlite3.Connection,
    video_and_clip_in_db: tuple[Video, Clip],
    clip: Clip,
    tmp_path: Path,
) -> None:
    db.execute(
        "UPDATE videos SET transcript_path = ? WHERE video_id = ?",
        ("/nonexistent/path.json", clip.video_id),
    )
    db.commit()

    result = _load_clip_transcript(clip, db, tmp_path / "transcripts")
    assert result == ""


# ---------------------------------------------------------------------------
# _build_metadata_prompt
# ---------------------------------------------------------------------------


def test_build_metadata_prompt_fills_placeholders(clip: Clip) -> None:
    result = _build_metadata_prompt(
        template=_SAMPLE_PROMPT_TEMPLATE,
        clip=clip,
        canal_fonte_nome="Flow Podcast",
        canal_fonte_handle="@FlowPodcast",
        video_title="Episódio 1",
        video_url="https://youtu.be/abc123XYZ01",
        clip_transcript="Brasil perde soberania.",
    )
    assert "Flow Podcast" in result
    assert "@FlowPodcast" in result
    assert "https://youtu.be/abc123XYZ01" in result
    assert "Brasil perde soberania industrial" in result
    assert "60s" in result  # duracao 90-30=60


def test_build_metadata_prompt_no_placeholders_remain(clip: Clip) -> None:
    result = _build_metadata_prompt(
        template=_SAMPLE_PROMPT_TEMPLATE,
        clip=clip,
        canal_fonte_nome="Canal",
        canal_fonte_handle="@handle",
        video_title="Título",
        video_url="https://youtu.be/x",
        clip_transcript="texto",
    )
    assert "{" not in result or "{{" not in result


# ---------------------------------------------------------------------------
# generate_metadata_for_clip
# ---------------------------------------------------------------------------


def test_generate_metadata_dry_run(
    db: sqlite3.Connection,
    video_and_clip_in_db: tuple[Video, Clip],
    clip: Clip,
    mock_llm: MagicMock,
    mock_canais_cfg: MagicMock,
    tmp_path: Path,
) -> None:
    result = generate_metadata_for_clip(
        clip=clip,
        conn=db,
        llm=mock_llm,
        model="claude-haiku-4-5",
        prompt_template=_SAMPLE_PROMPT_TEMPLATE,
        canais_cfg=mock_canais_cfg,
        transcripts_dir=tmp_path / "transcripts",
        dry_run=True,
    )
    assert result is True
    mock_llm.complete.assert_not_called()


def test_generate_metadata_success(
    db: sqlite3.Connection,
    video_and_clip_in_db: tuple[Video, Clip],
    clip: Clip,
    mock_llm: MagicMock,
    mock_canais_cfg: MagicMock,
    tmp_path: Path,
) -> None:
    result = generate_metadata_for_clip(
        clip=clip,
        conn=db,
        llm=mock_llm,
        model="claude-sonnet-4-6",
        prompt_template=_SAMPLE_PROMPT_TEMPLATE,
        canais_cfg=mock_canais_cfg,
        transcripts_dir=tmp_path / "transcripts",
    )
    assert result is True
    mock_llm.complete.assert_called_once()

    row = db.execute(
        "SELECT title, description, tags, status FROM clips WHERE clip_id = ?",
        (clip.clip_id,),
    ).fetchone()
    assert row["status"] == "metadata_ready"
    assert row["title"] == "Brasil perde soberania industrial"
    assert "Análise" in row["description"]
    tags = json.loads(row["tags"])
    assert isinstance(tags, list)
    assert len(tags) == 15


def test_generate_metadata_title_truncated(
    db: sqlite3.Connection,
    video_and_clip_in_db: tuple[Video, Clip],
    clip: Clip,
    mock_canais_cfg: MagicMock,
    tmp_path: Path,
) -> None:
    from canal_soberania.llm import LLMResponse

    long_title = "A" * 100
    response = json.dumps({"title": long_title, "description": "desc", "tags": ["t"] * 15})
    llm = MagicMock()
    llm.complete.return_value = LLMResponse(
        text=response, model="m", tokens_in=10, tokens_out=10, cost_usd=0.0
    )

    generate_metadata_for_clip(
        clip=clip,
        conn=db,
        llm=llm,
        model="claude-sonnet-4-6",
        prompt_template=_SAMPLE_PROMPT_TEMPLATE,
        canais_cfg=mock_canais_cfg,
        transcripts_dir=tmp_path / "transcripts",
    )
    row = db.execute("SELECT title FROM clips WHERE clip_id = ?", (clip.clip_id,)).fetchone()
    assert len(row["title"]) <= 60


def test_generate_metadata_invalid_json_returns_false(
    db: sqlite3.Connection,
    video_and_clip_in_db: tuple[Video, Clip],
    clip: Clip,
    mock_canais_cfg: MagicMock,
    tmp_path: Path,
) -> None:
    from canal_soberania.llm import LLMResponse

    llm = MagicMock()
    llm.complete.return_value = LLMResponse(
        text="não é json", model="m", tokens_in=10, tokens_out=5, cost_usd=0.0
    )

    result = generate_metadata_for_clip(
        clip=clip,
        conn=db,
        llm=llm,
        model="claude-sonnet-4-6",
        prompt_template=_SAMPLE_PROMPT_TEMPLATE,
        canais_cfg=mock_canais_cfg,
        transcripts_dir=tmp_path / "transcripts",
    )
    assert result is False
    row = db.execute("SELECT status FROM clips WHERE clip_id = ?", (clip.clip_id,)).fetchone()
    assert row["status"] != "metadata_ready"


def test_generate_metadata_empty_title_returns_false(
    db: sqlite3.Connection,
    video_and_clip_in_db: tuple[Video, Clip],
    clip: Clip,
    mock_canais_cfg: MagicMock,
    tmp_path: Path,
) -> None:
    from canal_soberania.llm import LLMResponse

    response = json.dumps({"title": "", "description": "desc", "tags": ["t"] * 15})
    llm = MagicMock()
    llm.complete.return_value = LLMResponse(
        text=response, model="m", tokens_in=10, tokens_out=10, cost_usd=0.0
    )

    result = generate_metadata_for_clip(
        clip=clip,
        conn=db,
        llm=llm,
        model="claude-sonnet-4-6",
        prompt_template=_SAMPLE_PROMPT_TEMPLATE,
        canais_cfg=mock_canais_cfg,
        transcripts_dir=tmp_path / "transcripts",
    )
    assert result is False


def test_generate_metadata_unknown_canal(
    db: sqlite3.Connection,
    video_and_clip_in_db: tuple[Video, Clip],
    clip: Clip,
    mock_llm: MagicMock,
    tmp_path: Path,
) -> None:
    empty_cfg = MagicMock()
    empty_cfg.canais = []

    result = generate_metadata_for_clip(
        clip=clip,
        conn=db,
        llm=mock_llm,
        model="claude-sonnet-4-6",
        prompt_template=_SAMPLE_PROMPT_TEMPLATE,
        canais_cfg=empty_cfg,
        transcripts_dir=tmp_path / "transcripts",
    )
    # Should still succeed (falls back to canal_id as nome)
    assert result is True
    row = db.execute("SELECT status FROM clips WHERE clip_id = ?", (clip.clip_id,)).fetchone()
    assert row["status"] == "metadata_ready"
