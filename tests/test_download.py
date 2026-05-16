"""Testes para stages/download.py (yt-dlp mockado)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.db import connect, get_videos_by_status, init_db, insert_video
from canal_soberania.models import Video
from canal_soberania.stages.download import (
    download_audio,
    download_video,
    download_video_assets,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def video() -> Video:
    return Video(
        video_id="dQw4w9WgXcQ",
        canal_id="flow_podcast",
        title="Soberania nacional em debate",
        published_at="2026-05-10T12:00:00Z",
        status="triage_caption_passed",
    )


# ---------------------------------------------------------------------------
# download_audio
# ---------------------------------------------------------------------------


def test_download_audio_returns_existing(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    existing = audio_dir / "dQw4w9WgXcQ.mp3"
    existing.write_bytes(b"fake_audio")
    result = download_audio("dQw4w9WgXcQ", audio_dir)
    assert result == existing


def test_download_audio_dry_run(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    result = download_audio("dQw4w9WgXcQ", audio_dir, dry_run=True)
    assert result is None
    assert not (audio_dir / "dQw4w9WgXcQ.mp3").exists()


def test_download_audio_yt_dlp_error(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    with patch("canal_soberania.stages.download.yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.download.side_effect = Exception("network error")
        result = download_audio("dQw4w9WgXcQ", audio_dir)
    assert result is None


def test_download_audio_success(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"

    def fake_download(urls: list[str]) -> None:
        (audio_dir / "dQw4w9WgXcQ.mp3").write_bytes(b"audio_data")

    with patch("canal_soberania.stages.download.yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.download.side_effect = fake_download
        result = download_audio("dQw4w9WgXcQ", audio_dir)
    assert result is not None
    assert result.name == "dQw4w9WgXcQ.mp3"


# ---------------------------------------------------------------------------
# download_video
# ---------------------------------------------------------------------------


def test_download_video_returns_existing(tmp_path: Path) -> None:
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    existing = video_dir / "dQw4w9WgXcQ.mp4"
    existing.write_bytes(b"fake_video")
    result = download_video("dQw4w9WgXcQ", video_dir)
    assert result == existing


def test_download_video_dry_run(tmp_path: Path) -> None:
    video_dir = tmp_path / "video"
    result = download_video("dQw4w9WgXcQ", video_dir, dry_run=True)
    assert result is None


def test_download_video_yt_dlp_error(tmp_path: Path) -> None:
    video_dir = tmp_path / "video"
    with patch("canal_soberania.stages.download.yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.download.side_effect = Exception("unavailable")
        result = download_video("dQw4w9WgXcQ", video_dir)
    assert result is None


# ---------------------------------------------------------------------------
# download_video_assets
# ---------------------------------------------------------------------------


def test_download_video_assets_success(
    db: sqlite3.Connection, video: Video, tmp_path: Path
) -> None:
    with db:
        insert_video(db, video)

    audio_dir = tmp_path / "audio"
    video_dir = tmp_path / "video"

    def fake_audio_download(urls: list[str]) -> None:
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / "dQw4w9WgXcQ.mp3").write_bytes(b"audio")

    def fake_video_download(urls: list[str]) -> None:
        video_dir.mkdir(parents=True, exist_ok=True)
        (video_dir / "dQw4w9WgXcQ.mp4").write_bytes(b"video")

    call_count = [0]

    def mock_download(urls: list[str]) -> None:
        call_count[0] += 1
        if call_count[0] == 1:
            fake_audio_download(urls)
        else:
            fake_video_download(urls)

    with patch("canal_soberania.stages.download.yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.download.side_effect = mock_download
        ok = download_video_assets(video, db, audio_dir, video_dir)

    assert ok is True
    downloaded = get_videos_by_status(db, "downloaded")
    assert len(downloaded) == 1
    assert downloaded[0].audio_path is not None
    assert downloaded[0].video_path is not None


def test_download_video_assets_audio_fail_sets_error(
    db: sqlite3.Connection, video: Video, tmp_path: Path
) -> None:
    with db:
        insert_video(db, video)

    audio_dir = tmp_path / "audio"
    video_dir = tmp_path / "video"

    with patch("canal_soberania.stages.download.yt_dlp.YoutubeDL") as mock_ydl:
        mock_ydl.return_value.__enter__.return_value.download.side_effect = Exception("blocked")
        ok = download_video_assets(video, db, audio_dir, video_dir)

    assert ok is False
    assert len(get_videos_by_status(db, "processing_error")) == 1


def test_download_video_assets_dry_run(
    db: sqlite3.Connection, video: Video, tmp_path: Path
) -> None:
    with db:
        insert_video(db, video)

    audio_dir = tmp_path / "audio"
    video_dir = tmp_path / "video"

    ok = download_video_assets(video, db, audio_dir, video_dir, dry_run=True)

    assert ok is True
    # Status deve permanecer inalterado
    assert len(get_videos_by_status(db, "triage_caption_passed")) == 1


def test_download_video_assets_video_fail_still_succeeds(
    db: sqlite3.Connection, video: Video, tmp_path: Path
) -> None:
    """Falha no vídeo não impede o pipeline — áudio é suficiente para transcrição."""
    with db:
        insert_video(db, video)

    audio_dir = tmp_path / "audio"
    video_dir = tmp_path / "video"
    audio_dir.mkdir()
    (audio_dir / "dQw4w9WgXcQ.mp3").write_bytes(b"audio")  # pré-existente

    with patch("canal_soberania.stages.download.yt_dlp.YoutubeDL") as mock_ydl:
        # Falha no download de vídeo (arquivo não criado)
        mock_ydl.return_value.__enter__.return_value.download.return_value = None
        ok = download_video_assets(video, db, audio_dir, video_dir)

    assert ok is True
    downloaded = get_videos_by_status(db, "downloaded")
    assert len(downloaded) == 1
    assert downloaded[0].audio_path is not None
    assert downloaded[0].video_path is None
