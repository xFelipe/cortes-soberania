"""Testes unitários para PipelineService."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.config import Settings
from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus
from canal_soberania.services.pipeline_service import PipelineService
from tests.fakes import InMemoryClipRepository, InMemoryVideoRepository

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


@pytest.fixture
def video_repo() -> InMemoryVideoRepository:
    return InMemoryVideoRepository()


@pytest.fixture
def clip_repo() -> InMemoryClipRepository:
    return InMemoryClipRepository()


@pytest.fixture
def service_mem(
    db: sqlite3.Connection,
    tmp_path: Path,
    video_repo: InMemoryVideoRepository,
    clip_repo: InMemoryClipRepository,
) -> PipelineService:
    settings = Settings(data_dir=tmp_path)
    paths: dict[str, Path] = {
        "data_dir": tmp_path,
        "db_path": tmp_path / "test.db",
        "schema_path": SCHEMA,
        "log_dir": tmp_path / "logs",
    }
    return PipelineService(
        conn=db,
        settings=settings,
        paths=paths,
        video_repo=video_repo,
        clip_repo=clip_repo,
    )


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
    insert_video(db, _make_video(video_id="bbbbbbbbb22", status=VideoStatus.TRIAGE_METADATA_PASSED))
    discovered = service.get_videos(status=VideoStatus.DISCOVERED)
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
    insert_clip(db, _make_clip(clip_id="dQw4w9WgXcQ_50_80", start_s=50.0, end_s=80.0, status=ClipStatus.EDITED))
    identified = service.get_clips(status=ClipStatus.IDENTIFIED)
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


# ---------------------------------------------------------------------------
# Testes com InMemory repos (sem SQLite)
# ---------------------------------------------------------------------------


def test_inmemory_get_video_not_found(
    service_mem: PipelineService,
) -> None:
    assert service_mem.get_video("xxxxxxxxxxx") is None


def test_inmemory_get_video_found(
    service_mem: PipelineService,
    video_repo: InMemoryVideoRepository,
) -> None:
    video = _make_video()
    video_repo.add(video)
    result = service_mem.get_video("dQw4w9WgXcQ")
    assert result is not None
    assert result.title == "Título de teste"


def test_inmemory_get_videos_all(
    service_mem: PipelineService,
    video_repo: InMemoryVideoRepository,
) -> None:
    video_repo.add(_make_video(video_id="aaaaaaaaa11"))
    video_repo.add(_make_video(video_id="bbbbbbbbb22"))
    assert len(service_mem.get_videos()) == 2


def test_inmemory_get_videos_by_status(
    service_mem: PipelineService,
    video_repo: InMemoryVideoRepository,
) -> None:
    video_repo.add(_make_video(video_id="aaaaaaaaa11", status=VideoStatus.DISCOVERED))
    video_repo.add(_make_video(video_id="bbbbbbbbb22", status=VideoStatus.TRIAGE_METADATA_PASSED))
    assert len(service_mem.get_videos(status=VideoStatus.DISCOVERED)) == 1


def test_inmemory_status_summary(
    service_mem: PipelineService,
    video_repo: InMemoryVideoRepository,
) -> None:
    video_repo.add(_make_video(video_id="aaaaaaaaa11", status=VideoStatus.DISCOVERED))
    video_repo.add(_make_video(video_id="bbbbbbbbb22", status=VideoStatus.DISCOVERED))
    video_repo.add(_make_video(video_id="ccccccccc33", status=VideoStatus.TRIAGE_METADATA_PASSED))
    summary = service_mem.get_status_summary()
    assert summary[VideoStatus.DISCOVERED] == 2
    assert summary[VideoStatus.TRIAGE_METADATA_PASSED] == 1


def test_inmemory_get_clips_all(
    service_mem: PipelineService,
    clip_repo: InMemoryClipRepository,
) -> None:
    clip_repo.add(_make_clip())
    assert len(service_mem.get_clips()) == 1


def test_inmemory_get_clips_by_status(
    service_mem: PipelineService,
    clip_repo: InMemoryClipRepository,
) -> None:
    clip_repo.add(_make_clip(clip_id="dQw4w9WgXcQ_10_40", status=ClipStatus.IDENTIFIED))
    clip_repo.add(_make_clip(clip_id="dQw4w9WgXcQ_50_80", start_s=50.0, end_s=80.0, status=ClipStatus.EDITED))
    assert len(service_mem.get_clips(status=ClipStatus.IDENTIFIED)) == 1
    assert len(service_mem.get_clips(status=ClipStatus.EDITED)) == 1


# ---------------------------------------------------------------------------
# Propagação para plataformas
# ---------------------------------------------------------------------------


def _make_service_with_mock_yt(
    tmp_path: Path,
    db: sqlite3.Connection,
    clip_repo: InMemoryClipRepository,
) -> tuple[PipelineService, MagicMock]:
    """Retorna (service, mock_youtube_client) com PlatformClient mockado."""
    yt_mock = MagicMock()
    settings = Settings(data_dir=tmp_path)
    paths: dict[str, Path] = {
        "data_dir": tmp_path,
        "db_path": tmp_path / "test.db",
        "schema_path": SCHEMA,
        "log_dir": tmp_path / "logs",
    }
    svc = PipelineService(
        conn=db,
        settings=settings,
        paths=paths,
        clip_repo=clip_repo,
        platforms={"youtube": yt_mock},
    )
    return svc, yt_mock


def test_update_clip_text_propagates_to_youtube_when_scheduled(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    """update_clip_text chama update_metadata no YouTube quando clipe está scheduled."""
    clip_repo = InMemoryClipRepository()
    clip_repo.add(_make_clip(
        clip_id="dQw4w9WgXcQ_10_40",
        status=ClipStatus.SCHEDULED_YOUTUBE,
        title="Título antigo",
        youtube_id="YT_001",
    ))
    svc, yt = _make_service_with_mock_yt(tmp_path, db, clip_repo)

    svc.update_clip_text(
        "dQw4w9WgXcQ_10_40",
        hook=None, payoff=None,
        title="Título novo",
        youtube_publish_at=None,
        description=None, tags=None,
    )

    yt.update_metadata.assert_called_once()
    args = yt.update_metadata.call_args
    assert args.args[0] == "YT_001"
    assert "#Shorts" in args.kwargs["title"]
    assert "Título novo" in args.kwargs["title"]


def test_update_clip_text_no_propagation_pre_upload(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    """Clipe em metadata_ready não chama update_metadata."""
    clip_repo = InMemoryClipRepository()
    clip_repo.add(_make_clip(
        clip_id="dQw4w9WgXcQ_10_40",
        status=ClipStatus.METADATA_READY,
        title="Título antigo",
    ))
    svc, yt = _make_service_with_mock_yt(tmp_path, db, clip_repo)

    svc.update_clip_text(
        "dQw4w9WgXcQ_10_40",
        hook=None, payoff=None,
        title="Título novo",
        youtube_publish_at=None,
    )

    yt.update_metadata.assert_not_called()


def test_unschedule_clip_calls_platform_and_transitions(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    """unschedule_clip chama yt.unschedule() e transiciona para unscheduled_youtube."""
    clip_repo = InMemoryClipRepository()
    clip_repo.add(_make_clip(
        clip_id="dQw4w9WgXcQ_10_40",
        status=ClipStatus.SCHEDULED_YOUTUBE,
        youtube_id="YT_002",
        youtube_id_horizontal="YT_002H",
    ))
    svc, yt = _make_service_with_mock_yt(tmp_path, db, clip_repo)

    svc.unschedule_clip("dQw4w9WgXcQ_10_40")

    assert yt.unschedule.call_count == 2  # vertical + horizontal
    clip = clip_repo.get("dQw4w9WgXcQ_10_40")
    assert clip is not None
    assert clip.status == ClipStatus.UNSCHEDULED_YOUTUBE


def test_discard_clip_deletes_and_transitions(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    """discard_clip chama yt.delete() para cada formato e transiciona para deleted_youtube."""
    clip_repo = InMemoryClipRepository()
    clip_repo.add(_make_clip(
        clip_id="dQw4w9WgXcQ_10_40",
        status=ClipStatus.SCHEDULED_YOUTUBE,
        youtube_id="YT_003",
        youtube_id_horizontal="YT_003H",
    ))
    svc, yt = _make_service_with_mock_yt(tmp_path, db, clip_repo)

    svc.discard_clip("dQw4w9WgXcQ_10_40")

    assert yt.delete.call_count == 2
    clip = clip_repo.get("dQw4w9WgXcQ_10_40")
    assert clip is not None
    assert clip.status == ClipStatus.DELETED_YOUTUBE
    assert clip.youtube_id is None
    assert clip.youtube_id_horizontal is None


def test_format_unchecked_deletes_upload(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    """Desmarcar render_horizontal com ID existente → delete() + coluna limpa."""
    clip_repo = InMemoryClipRepository()
    clip_repo.add(_make_clip(
        clip_id="dQw4w9WgXcQ_10_40",
        status=ClipStatus.SCHEDULED_YOUTUBE,
        youtube_id="YT_004",
        youtube_id_horizontal="YT_004H",
        render_vertical=True,
        render_horizontal=True,
    ))
    svc, yt = _make_service_with_mock_yt(tmp_path, db, clip_repo)

    svc.update_clip_text(
        "dQw4w9WgXcQ_10_40",
        hook=None, payoff=None, title=None,
        youtube_publish_at=None,
        render_vertical=True,
        render_horizontal=False,  # desmarcado
    )

    yt.delete.assert_called_once_with("YT_004H")
    clip = clip_repo.get("dQw4w9WgXcQ_10_40")
    assert clip is not None
    assert clip.youtube_id_horizontal is None
    # status deve ser scheduled_youtube (vertical ainda existe)
    assert clip.status == ClipStatus.SCHEDULED_YOUTUBE


def test_format_checked_marks_pending_reupload(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    """Marcar render_horizontal=True sem ID existente → salva flag, sem chamada de plataforma."""
    clip_repo = InMemoryClipRepository()
    clip_repo.add(_make_clip(
        clip_id="dQw4w9WgXcQ_10_40",
        status=ClipStatus.SCHEDULED_YOUTUBE,
        youtube_id="YT_005",
        youtube_id_horizontal=None,
        render_vertical=True,
        render_horizontal=False,  # estava desmarcado
    ))
    svc, yt = _make_service_with_mock_yt(tmp_path, db, clip_repo)

    svc.update_clip_text(
        "dQw4w9WgXcQ_10_40",
        hook=None, payoff=None, title=None,
        youtube_publish_at=None,
        render_vertical=True,
        render_horizontal=True,  # marcado novamente
    )

    yt.delete.assert_not_called()
    clip = clip_repo.get("dQw4w9WgXcQ_10_40")
    assert clip is not None
    assert clip.render_horizontal is True  # flag salvo
