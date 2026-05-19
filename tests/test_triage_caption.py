"""Testes para stages/triage_caption.py (yt-dlp e LLM mockados)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.config import CanaisConfig, Canal, Parametros
from canal_soberania.db import connect, get_videos_by_status, init_db, insert_video
from canal_soberania.llm import LLMResponse
from canal_soberania.models import Video, VideoStatus
from canal_soberania.stages.triage_caption import (
    _build_caption_prompt,
    _parse_caption_response,
    download_captions,
    parse_vtt,
    triage_video_caption,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"
PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts" / "triagem_caption.txt"
CRITERIOS = Path(__file__).parent.parent / "config" / "criterios_relevancia.md"

_SAMPLE_VTT = """\
WEBVTT
Kind: captions
Language: pt

00:00:00.000 --> 00:00:04.000
O Brasil precisa de soberania industrial.

00:00:04.000 --> 00:00:08.000
O pré-sal é um ativo estratégico nacional.

00:00:08.000 --> 00:00:12.000
O Brasil precisa de soberania industrial.

00:00:12.000 --> 00:00:16.000
Precisamos de política de <c>reindustrialização</c>.
"""


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
        title="Soberania industrial: o caso Embraer",
        description="Análise da importância da indústria nacional.",
        tags=["soberania", "industria", "embraer"],
        published_at="2026-05-10T12:00:00Z",
        duration_s=3600,
        status=VideoStatus.TRIAGE_METADATA_PASSED,
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
    llm.complete.return_value = LLMResponse(
        text=json.dumps({
            "score": score,
            "is_relevant": is_relevant,
            "fracao_tematica_estimada": 60,
            "themes_detected": ["economia_soberana", "industria"],
            "profundidade": "alta",
            "rationale": "Foco em soberania industrial",
        }),
        model="claude-haiku-4-5-20251001",
        tokens_in=1200,
        tokens_out=120,
        cost_usd=0.0018,
    )
    return llm


# ---------------------------------------------------------------------------
# parse_vtt
# ---------------------------------------------------------------------------


def test_parse_vtt_extracts_text(tmp_path: Path) -> None:
    vtt = tmp_path / "test.vtt"
    vtt.write_text(_SAMPLE_VTT, encoding="utf-8")
    result = parse_vtt(vtt)
    assert "soberania industrial" in result
    assert "pré-sal" in result
    assert "reindustrialização" in result


def test_parse_vtt_deduplicates(tmp_path: Path) -> None:
    vtt = tmp_path / "test.vtt"
    vtt.write_text(_SAMPLE_VTT, encoding="utf-8")
    result = parse_vtt(vtt)
    # "O Brasil precisa de soberania industrial." aparece 2x no VTT, deve deduplicar
    count = result.count("O Brasil precisa de soberania industrial.")
    assert count == 1


def test_parse_vtt_strips_html_tags(tmp_path: Path) -> None:
    vtt = tmp_path / "test.vtt"
    vtt.write_text(_SAMPLE_VTT, encoding="utf-8")
    result = parse_vtt(vtt)
    assert "<c>" not in result
    assert "</c>" not in result


def test_parse_vtt_respects_max_chars(tmp_path: Path) -> None:
    vtt = tmp_path / "big.vtt"
    lines = ["WEBVTT\n\n"]
    for i in range(500):
        lines.append(f"00:0{i//10}:{i%10:02d}:00.000 --> 00:0{i//10}:{i%10:02d}:04.000\n")
        lines.append(f"Linha de texto numero {i} com conteudo relevante sobre soberania.\n\n")
    vtt.write_text("".join(lines), encoding="utf-8")
    result = parse_vtt(vtt, max_chars=100)
    assert len(result) <= 100


# ---------------------------------------------------------------------------
# download_captions
# ---------------------------------------------------------------------------


def test_download_captions_returns_existing_file(tmp_path: Path) -> None:
    captions_dir = tmp_path / "captions"
    captions_dir.mkdir()
    existing = captions_dir / "dQw4w9WgXcQ.pt.vtt"
    existing.write_text("WEBVTT\n", encoding="utf-8")
    result = download_captions("dQw4w9WgXcQ", captions_dir)
    assert result == existing


def test_download_captions_dry_run_returns_none(tmp_path: Path) -> None:
    captions_dir = tmp_path / "captions"
    result = download_captions("dQw4w9WgXcQ", captions_dir, dry_run=True)
    assert result is None
    assert not (captions_dir / "dQw4w9WgXcQ.pt.vtt").exists()


def test_download_captions_yt_dlp_error_returns_none(tmp_path: Path) -> None:
    captions_dir = tmp_path / "captions"
    with patch("canal_soberania.stages.triage_caption.yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.download.side_effect = Exception("network error")
        result = download_captions("dQw4w9WgXcQ", captions_dir)
    assert result is None


def test_download_captions_yt_dlp_no_file_returns_none(tmp_path: Path) -> None:
    captions_dir = tmp_path / "captions"
    with patch("canal_soberania.stages.triage_caption.yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.download.return_value = None
        # yt-dlp "runs" but no file appears
        result = download_captions("dQw4w9WgXcQ", captions_dir)
    assert result is None


# ---------------------------------------------------------------------------
# _build_caption_prompt
# ---------------------------------------------------------------------------


def test_build_caption_prompt_fills_placeholders(
    prompt_template: str, criterios: str, video: Video
) -> None:
    result = _build_caption_prompt(
        prompt_template, criterios, video, "Arte da Guerra", "texto da caption"
    )
    assert "Embraer" in result
    assert "texto da caption" in result
    assert "60" in result  # 3600s / 60 = 60 min
    # Verifica que todos os placeholders foram substituídos
    for placeholder in ["{criterios_relevancia}", "{canal_nome}", "{title}", "{duracao_min}", "{caption_texto}"]:
        assert placeholder not in result


# ---------------------------------------------------------------------------
# _parse_caption_response
# ---------------------------------------------------------------------------


def test_parse_caption_response_valid() -> None:
    raw = json.dumps({
        "score": 7,
        "is_relevant": True,
        "fracao_tematica_estimada": 60,
        "themes_detected": ["industria"],
        "profundidade": "alta",
        "rationale": "ok",
    })
    result = _parse_caption_response(raw, "dQw4w9WgXcQ", "claude-haiku-4-5-20251001", 100, 50, 0.0)
    assert result.score == 7
    assert result.stage == "caption"
    assert result.is_relevant is True


# ---------------------------------------------------------------------------
# triage_video_caption integration
# ---------------------------------------------------------------------------


def _write_vtt(tmp_path: Path, video_id: str, lang: str = "pt") -> Path:
    captions_dir = tmp_path / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)
    vtt = captions_dir / f"{video_id}.{lang}.vtt"
    vtt.write_text(_SAMPLE_VTT, encoding="utf-8")
    return captions_dir


def test_triage_video_caption_passed(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
    tmp_path: Path,
) -> None:
    with db:
        insert_video(db, video)

    captions_dir = _write_vtt(tmp_path, video.video_id)
    llm = _make_llm(score=7, is_relevant=True)

    result = triage_video_caption(
        video=video, conn=db, llm=llm, model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg, captions_dir=captions_dir, threshold=6,
    )

    assert result is not None
    assert result.score == 7
    assert result.is_relevant is True
    assert len(get_videos_by_status(db, VideoStatus.TRIAGE_CAPTION_PASSED)) == 1


def test_triage_video_caption_rejected(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
    tmp_path: Path,
) -> None:
    with db:
        insert_video(db, video)

    captions_dir = _write_vtt(tmp_path, video.video_id)
    llm = _make_llm(score=3, is_relevant=False)

    result = triage_video_caption(
        video=video, conn=db, llm=llm, model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg, captions_dir=captions_dir, threshold=6,
    )

    assert result is not None
    assert result.is_relevant is False
    assert len(get_videos_by_status(db, VideoStatus.TRIAGE_CAPTION_REJECTED)) == 1


def test_triage_video_caption_skipped_when_no_caption(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
    tmp_path: Path,
) -> None:
    with db:
        insert_video(db, video)

    captions_dir = tmp_path / "captions"
    captions_dir.mkdir()
    # Nenhum arquivo VTT criado

    with patch("canal_soberania.stages.triage_caption.yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.download.return_value = None
        llm = _make_llm()
        result = triage_video_caption(
            video=video, conn=db, llm=llm, model="claude-haiku-4-5-20251001",
            prompt_template=prompt_template, criterios=criterios,
            canais_cfg=canais_cfg, captions_dir=captions_dir,
        )

    assert result is None
    llm.complete.assert_not_called()
    assert len(get_videos_by_status(db, VideoStatus.TRIAGE_CAPTION_SKIPPED)) == 1


def test_triage_video_caption_dry_run(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
    tmp_path: Path,
) -> None:
    with db:
        insert_video(db, video)

    captions_dir = _write_vtt(tmp_path, video.video_id)
    llm = _make_llm()

    result = triage_video_caption(
        video=video, conn=db, llm=llm, model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg, captions_dir=captions_dir, dry_run=True,
    )

    assert result is None
    llm.complete.assert_not_called()
    # Status deve permanecer inalterado (triage_metadata_passed)
    assert len(get_videos_by_status(db, VideoStatus.TRIAGE_METADATA_PASSED)) == 1


def test_triage_video_caption_llm_error(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
    tmp_path: Path,
) -> None:
    with db:
        insert_video(db, video)

    captions_dir = _write_vtt(tmp_path, video.video_id)
    llm = MagicMock()
    llm.complete.side_effect = RuntimeError("timeout")

    result = triage_video_caption(
        video=video, conn=db, llm=llm, model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg, captions_dir=captions_dir,
    )

    assert result is None
    assert len(get_videos_by_status(db, VideoStatus.PROCESSING_ERROR)) == 1


def test_triage_video_caption_saves_caption_path(
    db: sqlite3.Connection,
    video: Video,
    canais_cfg: CanaisConfig,
    prompt_template: str,
    criterios: str,
    tmp_path: Path,
) -> None:
    with db:
        insert_video(db, video)

    captions_dir = _write_vtt(tmp_path, video.video_id)
    llm = _make_llm()

    triage_video_caption(
        video=video, conn=db, llm=llm, model="claude-haiku-4-5-20251001",
        prompt_template=prompt_template, criterios=criterios,
        canais_cfg=canais_cfg, captions_dir=captions_dir,
    )

    row = db.execute(
        "SELECT caption_path FROM videos WHERE video_id = ?", (video.video_id,)
    ).fetchone()
    assert row["caption_path"] is not None
    assert "dQw4w9WgXcQ" in row["caption_path"]
