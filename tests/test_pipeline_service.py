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
MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        try:
            conn.executescript(sql_file.read_text())
        except Exception:  # noqa: BLE001
            pass


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    c = connect(db_path)
    _apply_migrations(c)
    return c


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


# ── pause / resume loop ───────────────────────────────────────────────────────

def test_pause_loop_creates_flag(service: PipelineService, tmp_path: Path) -> None:
    flag = tmp_path / ".pipeline_paused"
    assert not flag.exists()
    service.pause_loop()
    assert flag.exists()
    assert service.is_loop_paused() is True


def test_resume_loop_removes_flag(service: PipelineService, tmp_path: Path) -> None:
    service.pause_loop()
    assert service.is_loop_paused() is True
    service.resume_loop()
    assert service.is_loop_paused() is False
    assert not (tmp_path / ".pipeline_paused").exists()


def test_resume_loop_idempotent(service: PipelineService) -> None:
    service.resume_loop()  # no flag — must not raise
    assert service.is_loop_paused() is False


def test_is_loop_paused_default_false(service: PipelineService) -> None:
    assert service.is_loop_paused() is False


# ---------------------------------------------------------------------------
# run_sync_youtube + reset_stuck
# ---------------------------------------------------------------------------


def test_run_sync_youtube_delegates(service: PipelineService) -> None:
    with patch("canal_soberania.stages.sync_youtube.run") as mock_run:
        service.run_sync_youtube(dry_run=True)
        mock_run.assert_called_once_with(conn=service._conn, dry_run=True)


def test_reset_stuck_videos_delegates(
    service_mem: PipelineService, video_repo: InMemoryVideoRepository
) -> None:
    count = service_mem.reset_stuck_videos()
    assert count == 0  # InMemory sempre retorna 0


def test_reset_stuck_clips_delegates(
    service_mem: PipelineService, clip_repo: InMemoryClipRepository
) -> None:
    count = service_mem.reset_stuck_clips()
    assert count == 0


# ---------------------------------------------------------------------------
# run_pipeline_auto
# ---------------------------------------------------------------------------


def test_run_pipeline_auto_runs_all_stages(service: PipelineService) -> None:
    called: list[str] = []

    def mock_stage(name: str):  # type: ignore[return]
        def fn(dry_run: bool = False) -> None:
            called.append(name)
        return fn

    with (
        patch.object(service, "run_triage_metadata", mock_stage("triage_metadata")),
        patch.object(service, "run_triage_caption", mock_stage("triage_caption")),
        patch.object(service, "run_download", mock_stage("download")),
        patch.object(service, "run_transcribe", mock_stage("transcribe")),
        patch.object(service, "run_triage_transcript", mock_stage("triage_transcript")),
        patch.object(service, "run_find_clips", mock_stage("find_clips")),
        patch.object(service, "run_edit", mock_stage("edit")),
        patch.object(service, "run_thumbnail", mock_stage("thumbnail")),
        patch.object(service, "run_generate_metadata", mock_stage("generate_metadata")),
    ):
        service.run_pipeline_auto()

    assert "triage_metadata" in called
    assert "edit" in called
    assert len(called) == 9


def test_run_pipeline_auto_continues_after_stage_error(service: PipelineService) -> None:
    """Erros em um stage não interrompem os seguintes."""
    called: list[str] = []

    def fail_stage(dry_run: bool = False) -> None:
        raise RuntimeError("stage error")

    def ok_stage(dry_run: bool = False) -> None:
        called.append("ok")

    with (
        patch.object(service, "run_triage_metadata", fail_stage),
        patch.object(service, "run_triage_caption", ok_stage),
        patch.object(service, "run_download", ok_stage),
        patch.object(service, "run_transcribe", ok_stage),
        patch.object(service, "run_triage_transcript", ok_stage),
        patch.object(service, "run_find_clips", ok_stage),
        patch.object(service, "run_edit", ok_stage),
        patch.object(service, "run_thumbnail", ok_stage),
        patch.object(service, "run_generate_metadata", ok_stage),
    ):
        service.run_pipeline_auto()

    assert len(called) == 8


def test_run_pipeline_auto_stops_when_cancelled(service: PipelineService) -> None:
    service.cancel()
    called: list[str] = []

    with patch.object(service, "run_triage_metadata", lambda dry_run=False: called.append("x")):
        service.run_pipeline_auto()

    assert called == []


# ---------------------------------------------------------------------------
# get_clip / approve_video / reject_video / approve_clip / reject_clip / restore_clip
# ---------------------------------------------------------------------------


def test_get_clip_found(
    service_mem: PipelineService, clip_repo: InMemoryClipRepository
) -> None:
    clip_repo.add(_make_clip())
    result = service_mem.get_clip("dQw4w9WgXcQ_10_40")
    assert result is not None
    assert result.clip_id == "dQw4w9WgXcQ_10_40"


def test_get_clip_not_found(service_mem: PipelineService) -> None:
    assert service_mem.get_clip("nonexistent") is None


def test_approve_video_discovered(
    service_mem: PipelineService, video_repo: InMemoryVideoRepository
) -> None:
    video_repo.add(_make_video(status=VideoStatus.DISCOVERED))
    service_mem.approve_video("dQw4w9WgXcQ")
    updated = video_repo.get("dQw4w9WgXcQ")
    assert updated is not None
    assert updated.status == VideoStatus.TRIAGE_METADATA_PASSED


def test_approve_video_not_found(service_mem: PipelineService) -> None:
    with pytest.raises(ValueError, match="não encontrado"):
        service_mem.approve_video("nonexistent")


def test_approve_video_unaprovable_status(
    service_mem: PipelineService, video_repo: InMemoryVideoRepository
) -> None:
    video_repo.add(_make_video(status=VideoStatus.CLIPS_FOUND))
    with pytest.raises(ValueError, match="não aprovável"):
        service_mem.approve_video("dQw4w9WgXcQ")


def test_reject_video(
    service_mem: PipelineService, video_repo: InMemoryVideoRepository
) -> None:
    video_repo.add(_make_video(status=VideoStatus.DISCOVERED))
    service_mem.reject_video("dQw4w9WgXcQ")
    updated = video_repo.get("dQw4w9WgXcQ")
    assert updated is not None
    assert updated.status == VideoStatus.TRIAGE_METADATA_REJECTED


def test_approve_clip_metadata_ready(
    service_mem: PipelineService, clip_repo: InMemoryClipRepository
) -> None:
    clip_repo.add(_make_clip(status=ClipStatus.METADATA_READY))
    service_mem.approve_clip("dQw4w9WgXcQ_10_40")
    updated = clip_repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.status == ClipStatus.SCHEDULED_YOUTUBE


def test_approve_clip_not_found(service_mem: PipelineService) -> None:
    with pytest.raises(ValueError, match="não encontrado"):
        service_mem.approve_clip("nonexistent")


def test_approve_clip_unaprovable(
    service_mem: PipelineService, clip_repo: InMemoryClipRepository
) -> None:
    clip_repo.add(_make_clip(status=ClipStatus.UPLOADING_YOUTUBE))
    with pytest.raises(ValueError, match="não aprovável"):
        service_mem.approve_clip("dQw4w9WgXcQ_10_40")


def test_reject_clip(
    service_mem: PipelineService, clip_repo: InMemoryClipRepository
) -> None:
    clip_repo.add(_make_clip(status=ClipStatus.METADATA_READY))
    service_mem.reject_clip("dQw4w9WgXcQ_10_40", reason="Fora do tema")
    updated = clip_repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.status == ClipStatus.PROCESSING_ERROR
    assert updated.error_message == "Fora do tema"


def test_restore_clip(
    service_mem: PipelineService, clip_repo: InMemoryClipRepository
) -> None:
    clip_repo.add(_make_clip(status=ClipStatus.PROCESSING_ERROR))
    service_mem.restore_clip("dQw4w9WgXcQ_10_40")
    updated = clip_repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.status == ClipStatus.IDENTIFIED


def test_update_clip_text_not_found(service_mem: PipelineService) -> None:
    with pytest.raises(ValueError, match="não encontrado"):
        service_mem.update_clip_text(
            "nonexistent",
            hook="h", payoff="p", title="t",
            youtube_publish_at=None,
        )


# ---------------------------------------------------------------------------
# mark_video_burned_subtitles
# ---------------------------------------------------------------------------


def test_mark_video_burned_subtitles_with_subs(
    service: PipelineService, db: sqlite3.Connection
) -> None:
    from canal_soberania.db import insert_clip, insert_video
    insert_video(db, _make_video())
    clip = _make_clip(clip_id="dQw4w9WgXcQ_10_40", status=ClipStatus.EDITED)
    insert_clip(db, clip)

    count = service.mark_video_burned_subtitles("dQw4w9WgXcQ", has_subs=True)
    assert count >= 1

    row = db.execute("SELECT status FROM clips WHERE clip_id = ?", ("dQw4w9WgXcQ_10_40",)).fetchone()
    assert row["status"] == ClipStatus.IDENTIFIED


def test_mark_video_burned_subtitles_without_subs(
    service: PipelineService, db: sqlite3.Connection
) -> None:
    from canal_soberania.db import insert_video
    insert_video(db, _make_video())

    count = service.mark_video_burned_subtitles("dQw4w9WgXcQ", has_subs=False)
    assert count == 0


# ---------------------------------------------------------------------------
# update_clip_trim
# ---------------------------------------------------------------------------


def test_update_clip_trim_requeues(
    service: PipelineService, db: sqlite3.Connection
) -> None:
    from canal_soberania.db import insert_clip, insert_video
    insert_video(db, _make_video())
    clip = _make_clip(clip_id="dQw4w9WgXcQ_10_40", status=ClipStatus.EDITED)
    insert_clip(db, clip)

    service.update_clip_trim("dQw4w9WgXcQ_10_40", start_s=15.0, end_s=45.0)

    row = db.execute(
        "SELECT start_s, end_s, status FROM clips WHERE clip_id = ?",
        ("dQw4w9WgXcQ_10_40",),
    ).fetchone()
    assert row["start_s"] == 15.0
    assert row["end_s"] == 45.0
    assert row["status"] == ClipStatus.IDENTIFIED


def test_update_clip_trim_invalid(service: PipelineService) -> None:
    with pytest.raises(ValueError, match="end_s deve ser maior"):
        service.update_clip_trim("dQw4w9WgXcQ_10_40", start_s=50.0, end_s=20.0)


# ---------------------------------------------------------------------------
# Gestão de canais
# ---------------------------------------------------------------------------


def _make_canal(**kwargs: object) -> "Canal":  # type: ignore[return]
    from canal_soberania.config import Canal
    defaults: dict[str, object] = {
        "id": "canal_teste",
        "nome": "Canal Teste",
        "handle": "@teste",
        "channel_url": "https://youtube.com/@teste",
        "tema_primario": "soberania",
    }
    defaults.update(kwargs)
    return Canal.model_validate(defaults)


def test_get_canais_empty(service: PipelineService) -> None:
    assert service.get_canais() == []


def test_upsert_and_get_canal(service: PipelineService) -> None:
    canal = _make_canal()
    service.upsert_canal(canal)
    canais = service.get_canais()
    assert len(canais) == 1
    assert canais[0].id == "canal_teste"


def test_upsert_canal_updates(service: PipelineService) -> None:
    service.upsert_canal(_make_canal(nome="Antigo"))
    service.upsert_canal(_make_canal(nome="Atualizado"))
    canais = service.get_canais()
    assert len(canais) == 1
    assert canais[0].nome == "Atualizado"


def test_get_canais_apenas_ativos(service: PipelineService) -> None:
    service.upsert_canal(_make_canal(id="ativo1", ativo=True))
    service.upsert_canal(_make_canal(id="inativo1", ativo=False))
    assert len(service.get_canais(apenas_ativos=True)) == 1
    assert len(service.get_canais(apenas_ativos=False)) == 2


def test_toggle_canal_ativo(service: PipelineService) -> None:
    service.upsert_canal(_make_canal(ativo=True))
    service.toggle_canal_ativo("canal_teste", False)
    canais = service.get_canais(apenas_ativos=True)
    assert canais == []


def test_delete_canal(service: PipelineService) -> None:
    service.upsert_canal(_make_canal())
    service.delete_canal("canal_teste")
    assert service.get_canais() == []


# ---------------------------------------------------------------------------
# add_video_by_id (mock Google API)
# ---------------------------------------------------------------------------


def test_add_video_by_id_no_api_key(service: PipelineService) -> None:
    with pytest.raises(ValueError, match="youtube_api_key"):
        service.add_video_by_id("dQw4w9WgXcQ")


def test_add_video_by_id_not_found(
    service: PipelineService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake")
    service._settings = service._settings.model_copy(update={"youtube_api_key": "fake"})

    with patch("googleapiclient.discovery.build") as mock_build:
        mock_yt = MagicMock()
        mock_build.return_value = mock_yt
        with patch("canal_soberania.stages.discover.fetch_video_details", return_value=[]):
            with pytest.raises(ValueError, match="não encontrado"):
                service.add_video_by_id("dQw4w9WgXcQ")


def test_add_video_by_id_success(
    service: PipelineService, db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    service._settings = service._settings.model_copy(update={"youtube_api_key": "fake"})

    fake_item = {
        "snippet": {
            "title": "Soberania Nacional",
            "description": "Desc",
            "tags": ["soberania"],
            "publishedAt": "2024-01-01T00:00:00Z",
        },
        "statistics": {"viewCount": "1000", "likeCount": "100"},
        "contentDetails": {"duration": "PT5M30S"},
    }

    with patch("googleapiclient.discovery.build") as mock_build:
        mock_build.return_value = MagicMock()
        with patch("canal_soberania.stages.discover.fetch_video_details", return_value=[fake_item]):
            video = service.add_video_by_id("dQw4w9WgXcQ")

    assert video.title == "Soberania Nacional"
    assert video.canal_id == "manual"
    row = db.execute("SELECT 1 FROM videos WHERE video_id = ?", ("dQw4w9WgXcQ",)).fetchone()
    assert row is not None


def test_add_video_by_id_already_exists(
    service: PipelineService, db: sqlite3.Connection
) -> None:
    from canal_soberania.db import insert_video
    insert_video(db, _make_video())
    service._settings = service._settings.model_copy(update={"youtube_api_key": "fake"})

    fake_item = {
        "snippet": {"title": "T", "publishedAt": "2024-01-01T00:00:00Z"},
        "statistics": {},
        "contentDetails": {},
    }
    with patch("googleapiclient.discovery.build") as mock_build:
        mock_build.return_value = MagicMock()
        with patch("canal_soberania.stages.discover.fetch_video_details", return_value=[fake_item]):
            with pytest.raises(ValueError, match="já está no banco"):
                service.add_video_by_id("dQw4w9WgXcQ")
