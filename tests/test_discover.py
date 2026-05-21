"""Testes para stages/discover.py (YouTube API mockada)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from canal_soberania.config import Canal, Parametros
from canal_soberania.db import connect, get_videos_by_status, init_db
from canal_soberania.models import VideoStatus
from canal_soberania.stages.discover import (
    _iso_cutoff,
    _parse_duration,
    discover_canal,
    fetch_recent_video_ids,
    fetch_video_details,
    get_uploads_playlist_id,
    run as discover_run,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def canal() -> Canal:
    return Canal(
        id="flow_podcast",
        nome="Flow Podcast",
        handle="@FlowPodcast",
        channel_url="https://www.youtube.com/@FlowPodcast",
        tema_primario="variado",
    )


@pytest.fixture
def params() -> Parametros:
    return Parametros(janela_dias_discover=7, max_videos_por_canal_por_run=20)


def _recent_iso(days_ago: int = 2) -> str:
    """Retorna uma data ISO 8601 relativa a agora, para evitar testes sensíveis a data."""
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_youtube_mock(
    *,
    playlist_id: str = "UU_abc123",
    video_ids: list[str] | None = None,
    video_details: list[dict[str, Any]] | None = None,
) -> MagicMock:
    if video_ids is None:
        video_ids = ["dQw4w9WgXcQ", "abc12345678"]
    recent = _recent_iso(days_ago=2)
    if video_details is None:
        video_details = [
            {
                "id": vid,
                "snippet": {
                    "title": f"Vídeo {vid}",
                    "description": "Descrição do vídeo",
                    "publishedAt": recent,
                    "tags": ["geopolitica", "soberania"],
                },
                "contentDetails": {"duration": "PT1H2M30S"},
                "statistics": {
                    "viewCount": "1000",
                    "likeCount": "100",
                    "commentCount": "50",
                },
            }
            for vid in video_ids
        ]

    yt = MagicMock()

    # channels().list().execute() → retorna playlist_id
    yt.channels.return_value.list.return_value.execute.return_value = {
        "items": [
            {"contentDetails": {"relatedPlaylists": {"uploads": playlist_id}}}
        ]
    }

    # playlistItems().list().execute() → vídeos recentes
    playlist_items = [
        {
            "snippet": {"publishedAt": recent},
            "contentDetails": {"videoId": vid},
        }
        for vid in video_ids
    ]
    yt.playlistItems.return_value.list.return_value.execute.return_value = {
        "items": playlist_items,
        "nextPageToken": None,
    }

    # videos().list().execute() → detalhes completos
    yt.videos.return_value.list.return_value.execute.return_value = {
        "items": video_details
    }

    return yt


# ---------------------------------------------------------------------------
# Testes unitários de helpers
# ---------------------------------------------------------------------------


def test_parse_duration_full() -> None:
    assert _parse_duration("PT1H2M30S") == 3750


def test_parse_duration_minutes_only() -> None:
    assert _parse_duration("PT45M") == 2700


def test_parse_duration_seconds_only() -> None:
    assert _parse_duration("PT30S") == 30


def test_parse_duration_invalid() -> None:
    assert _parse_duration("") is None
    assert _parse_duration("invalido") is None


def test_iso_cutoff_format() -> None:
    cutoff = _iso_cutoff(7)
    assert cutoff.endswith("Z")
    assert "T" in cutoff


def test_get_uploads_playlist_id() -> None:
    yt = _make_youtube_mock(playlist_id="UU_test123")
    result = get_uploads_playlist_id(yt, "@FlowPodcast")
    assert result == "UU_test123"
    yt.channels.return_value.list.assert_called_once_with(
        part="contentDetails", forHandle="FlowPodcast"
    )


def test_get_uploads_playlist_id_not_found() -> None:
    yt = MagicMock()
    yt.channels.return_value.list.return_value.execute.return_value = {"items": []}
    result = get_uploads_playlist_id(yt, "@desconhecido")
    assert result is None


def test_fetch_recent_video_ids_respects_cutoff() -> None:
    yt = MagicMock()
    new_date = _recent_iso(days_ago=2)
    yt.playlistItems.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "snippet": {"publishedAt": new_date},
                "contentDetails": {"videoId": "vid_new111111"},
            },
            {
                "snippet": {"publishedAt": "2020-01-01T00:00:00Z"},  # muito antigo
                "contentDetails": {"videoId": "vid_old111111"},
            },
        ],
        "nextPageToken": None,
    }
    # cutoff = 7 dias atrás; new_date está dentro, 2020-01-01 está fora
    cutoff = _iso_cutoff(7)
    result = fetch_recent_video_ids(yt, "UU_abc", cutoff, 20)
    assert "vid_new111111" in result
    assert "vid_old111111" not in result


def test_fetch_video_details_batches() -> None:
    yt = MagicMock()
    yt.videos.return_value.list.return_value.execute.return_value = {"items": [{"id": "x"}]}
    results = fetch_video_details(yt, ["a"] * 60)
    assert yt.videos.return_value.list.call_count == 2  # 60 vídeos → 2 batches de 50


# ---------------------------------------------------------------------------
# Testes de integração (discover_canal com DB real)
# ---------------------------------------------------------------------------


def test_discover_canal_inserts_videos(
    db: sqlite3.Connection, canal: Canal, params: Parametros
) -> None:
    yt = _make_youtube_mock(video_ids=["dQw4w9WgXcQ", "abc12345678"])
    inserted, skipped = discover_canal(yt, canal, params, db)
    assert inserted == 2
    assert skipped == 0
    videos = get_videos_by_status(db, VideoStatus.DISCOVERED)
    assert len(videos) == 2
    assert {v.video_id for v in videos} == {"dQw4w9WgXcQ", "abc12345678"}


def test_discover_canal_idempotent(
    db: sqlite3.Connection, canal: Canal, params: Parametros
) -> None:
    yt = _make_youtube_mock(video_ids=["dQw4w9WgXcQ"])
    discover_canal(yt, canal, params, db)
    inserted, skipped = discover_canal(yt, canal, params, db)
    assert inserted == 0
    assert skipped == 1
    videos = get_videos_by_status(db, VideoStatus.DISCOVERED)
    assert len(videos) == 1


def test_discover_canal_dry_run_does_not_insert(
    db: sqlite3.Connection, canal: Canal, params: Parametros
) -> None:
    yt = _make_youtube_mock(video_ids=["dQw4w9WgXcQ"])
    inserted, _ = discover_canal(yt, canal, params, db, dry_run=True)
    assert inserted == 1  # contado mas não persistido
    videos = get_videos_by_status(db, VideoStatus.DISCOVERED)
    assert len(videos) == 0


def test_discover_canal_parses_metadata(
    db: sqlite3.Connection, canal: Canal, params: Parametros
) -> None:
    yt = _make_youtube_mock(video_ids=["dQw4w9WgXcQ"])
    discover_canal(yt, canal, params, db)
    videos = get_videos_by_status(db, VideoStatus.DISCOVERED)
    v = videos[0]
    assert v.duration_s == 3750  # PT1H2M30S
    assert v.view_count == 1000
    assert v.like_count == 100
    assert v.tags == ["geopolitica", "soberania"]
    assert v.canal_id == "flow_podcast"


def test_discover_canal_no_playlist(
    db: sqlite3.Connection, canal: Canal, params: Parametros
) -> None:
    yt = MagicMock()
    yt.channels.return_value.list.return_value.execute.return_value = {"items": []}
    inserted, skipped = discover_canal(yt, canal, params, db)
    assert inserted == 0
    assert skipped == 0


# ---------------------------------------------------------------------------
# Testes do run() multi-canal
# ---------------------------------------------------------------------------


def _seed_output_canal(
    conn: sqlite3.Connection,
    output_canal_id: str = "soberania",
    fonte_canal_id: str = "flow_podcast",
) -> None:
    """Popula output_canais + canais + output_canal_fontes para testes do run()."""
    conn.execute(
        "INSERT OR IGNORE INTO canais (id, nome, handle, channel_url, tema_primario) VALUES (?,?,?,?,?)",
        (fonte_canal_id, "Flow Podcast", "@FlowPodcast", "https://youtube.com/@FlowPodcast", "variado"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO output_canais (id, nome, tema) VALUES (?,?,?)",
        (output_canal_id, "Canal Soberania", "Soberania nacional"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO output_canal_fontes (output_canal_id, fonte_canal_id) VALUES (?,?)",
        (output_canal_id, fonte_canal_id),
    )
    conn.commit()


def test_run_multichannel_inserts_with_target_canal_id(db: sqlite3.Connection) -> None:
    """run() modo multi-canal deve inserir vídeos com target_canal_id correto."""
    _seed_output_canal(db, output_canal_id="soberania", fonte_canal_id="flow_podcast")
    yt = _make_youtube_mock(video_ids=["runMCvideo1"])

    discover_run(youtube=yt, conn=db, janela_dias=7)

    row = db.execute(
        "SELECT target_canal_id FROM videos WHERE video_id = ?", ("runMCvideo1",)
    ).fetchone()
    assert row is not None
    assert row[0] == "soberania"


def test_run_multichannel_specific_output_canal(db: sqlite3.Connection) -> None:
    """run(output_canal_id=...) deve processar apenas o canal de saída especificado."""
    _seed_output_canal(db, output_canal_id="soberania", fonte_canal_id="flow_podcast")
    yt = _make_youtube_mock(video_ids=["runSpecVid1"])

    discover_run(youtube=yt, conn=db, output_canal_id="soberania", janela_dias=7)

    row = db.execute(
        "SELECT target_canal_id FROM videos WHERE video_id = ?", ("runSpecVid1",)
    ).fetchone()
    assert row is not None
    assert row[0] == "soberania"


def test_run_multichannel_no_fontes_skips_output_canal(db: sqlite3.Connection) -> None:
    """Output canal sem fontes não deve causar erro — apenas avisa e continua."""
    # Insere output canal sem fontes
    db.execute(
        "INSERT OR IGNORE INTO output_canais (id, nome, tema) VALUES (?,?,?)",
        ("vazio", "Canal Vazio", "Sem fontes"),
    )
    db.commit()
    yt = _make_youtube_mock()

    # Não deve levantar exceção
    discover_run(youtube=yt, conn=db, janela_dias=7)

    count = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    assert count == 0


def test_run_fallback_no_output_canais(db: sqlite3.Connection) -> None:
    """Quando não há output_canais, run() cai no modo fallback (canais ativos direto)."""
    db.execute(
        "INSERT OR IGNORE INTO canais (id, nome, handle, channel_url, tema_primario, ativo) VALUES (?,?,?,?,?,?)",
        ("fb_canal", "Fallback Canal", "@fbcanal", "https://youtube.com/@fbcanal", "variado", 1),
    )
    db.commit()

    yt = _make_youtube_mock(video_ids=["fbFallbk011"])

    discover_run(youtube=yt, conn=db, janela_dias=7)

    row = db.execute(
        "SELECT target_canal_id FROM videos WHERE video_id = ?", ("fbFallbk011",)
    ).fetchone()
    assert row is not None
    assert row[0] == "soberania"  # valor default


def test_run_no_youtube_api_key_aborts(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    """run() sem chave da API e sem youtube mockado deve retornar sem inserir nada."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "")
    discover_run(conn=db, janela_dias=7)  # youtube=None, sem chave
    count = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    assert count == 0
