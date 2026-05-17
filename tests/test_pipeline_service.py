"""Testes unitários para PipelineService."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from canal_soberania.config import Settings
from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, Video
from canal_soberania.services.pipeline_service import PipelineService

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def service(db: sqlite3.Connection, tmp_path: Path) -> PipelineService:
    settings = Settings(data_dir=tmp_path)
    paths: dict[str, Path] = {
        "data_dir": tmp_path,
        "db_path": tmp_path / "test.db",
        "schema_path": SCHEMA,
        "log_dir": tmp_path / "logs",
    }
    return PipelineService(conn=db, settings=settings, paths=paths)


def _make_video(**kwargs: object) -> Video:
    defaults: dict[str, object] = {
        "video_id": "dQw4w9WgXcQ",
        "canal_id": "flow_podcast",
        "title": "Título de teste",
        "published_at": "2024-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    return Video.model_validate(defaults)


def _make_clip(**kwargs: object) -> Clip:
    defaults: dict[str, object] = {
        "clip_id": "dQw4w9WgXcQ_10_40",
        "video_id": "dQw4w9WgXcQ",
        "start_s": 10.0,
        "end_s": 40.0,
    }
    defaults.update(kwargs)
    return Clip.model_validate(defaults)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def test_get_status_summary_empty(service: PipelineService) -> None:
    assert service.get_status_summary() == {}


def test_get_status_summary_with_videos(
    service: PipelineService, db: sqlite3.Connection
) -> None:
    insert_video(db, _make_video(video_id="aaaaaaaaa11"))
    insert_video(db, _make_video(video_id="bbbbbbbbb22"))
    summary = service.get_status_summary()
    assert summary.get("discovered", 0) == 2


def test_get_monthly_cost_zero(service: PipelineService) -> None:
    assert service.get_monthly_cost() == 0.0


def test_get_video_not_found(service: PipelineService) -> None:
    assert service.get_video("xxxxxxxxxxx") is None


def test_get_video_found(service: PipelineService, db: sqlite3.Connection) -> None:
    video = _make_video()
    insert_video(db, video)
    result = service.get_video("dQw4w9WgXcQ")
    assert result is not None
    assert result.video_id == "dQw4w9WgXcQ"
    assert result.title == "Título de teste"


def test_get_videos_all(service: PipelineService, db: sqlite3.Connection) -> None:
    insert_video(db, _make_video(video_id="aaaaaaaaa11"))
    insert_video(db, _make_video(video_id="bbbbbbbbb22"))
    videos = service.get_videos()
    assert len(videos) == 2


def test_get_videos_by_status(service: PipelineService, db: sqlite3.Connection) -> None:
    insert_video(db, _make_video(video_id="aaaaaaaaa11"))
    insert_video(db, _make_video(video_id="bbbbbbbbb22", status="triage_metadata_passed"))
    discovered = service.get_videos(status="discovered")
    assert len(discovered) == 1
    assert discovered[0].video_id == "aaaaaaaaa11"


def test_get_clips_empty(service: PipelineService) -> None:
    assert service.get_clips() == []


def test_get_clips_all(service: PipelineService, db: sqlite3.Connection) -> None:
    insert_video(db, _make_video())
    insert_clip(db, _make_clip())
    clips = service.get_clips()
    assert len(clips) == 1
    assert clips[0].clip_id == "dQw4w9WgXcQ_10_40"


def test_get_clips_by_status(service: PipelineService, db: sqlite3.Connection) -> None:
    insert_video(db, _make_video())
    insert_clip(db, _make_clip(clip_id="dQw4w9WgXcQ_10_40"))
    insert_clip(db, _make_clip(clip_id="dQw4w9WgXcQ_50_80", start_s=50.0, end_s=80.0, status="edited"))
    identified = service.get_clips(status="identified")
    assert len(identified) == 1
    assert identified[0].clip_id == "dQw4w9WgXcQ_10_40"


# ---------------------------------------------------------------------------
# Stage delegation (smoke tests — verifica que PipelineService delega corretamente)
# ---------------------------------------------------------------------------


def test_run_discover_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.discover.run") as mock_run:
        service.run_discover(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_triage_metadata_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.triage_metadata.run") as mock_run:
        service.run_triage_metadata(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_triage_caption_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.triage_caption.run") as mock_run:
        service.run_triage_caption(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_triage_transcript_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.triage_transcript.run") as mock_run:
        service.run_triage_transcript(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_download_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.download.run") as mock_run:
        service.run_download(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_transcribe_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.transcribe.run") as mock_run:
        service.run_transcribe(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_find_clips_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.find_clips.run") as mock_run:
        service.run_find_clips(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_edit_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.edit.run") as mock_run:
        service.run_edit(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_thumbnail_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.thumbnail.run") as mock_run:
        service.run_thumbnail(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_generate_metadata_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.metadata.run") as mock_run:
        service.run_generate_metadata(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_upload_youtube_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.upload_youtube.run") as mock_run:
        service.run_upload_youtube(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_run_upload_tiktok_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.upload_tiktok.run") as mock_run:
        service.run_upload_tiktok(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)
