"""Testes para VideoStateMachine e ClipStateMachine."""

from __future__ import annotations

import pytest

from canal_soberania.core.state import (
    CLIP_TRANSITIONS,
    VIDEO_TRANSITIONS,
    ClipStateMachine,
    InvalidTransitionError,
    VideoStateMachine,
)
from canal_soberania.models import ClipStatus, VideoStatus

# ---------------------------------------------------------------------------
# VideoStateMachine
# ---------------------------------------------------------------------------


def test_video_valid_transition_discovered_to_passed() -> None:
    VideoStateMachine.transition("vid001", VideoStatus.DISCOVERED, VideoStatus.TRIAGE_METADATA_PASSED)


def test_video_valid_transition_discovered_to_rejected() -> None:
    VideoStateMachine.transition("vid001", VideoStatus.DISCOVERED, VideoStatus.TRIAGE_METADATA_REJECTED)


def test_video_valid_transition_to_downloading() -> None:
    VideoStateMachine.transition("vid001", VideoStatus.TRIAGE_CAPTION_PASSED, VideoStatus.DOWNLOADING)


def test_video_valid_transition_downloading_retry() -> None:
    VideoStateMachine.transition("vid001", VideoStatus.DOWNLOADING, VideoStatus.DISCOVERED)


def test_video_valid_transition_to_clips_found() -> None:
    VideoStateMachine.transition("vid001", VideoStatus.FINDING_CLIPS, VideoStatus.CLIPS_FOUND)


def test_video_invalid_transition_raises() -> None:
    with pytest.raises(InvalidTransitionError, match="discovered"):
        VideoStateMachine.transition("vid001", VideoStatus.CLIPS_FOUND, VideoStatus.DISCOVERED)


def test_video_invalid_transition_skip_state() -> None:
    with pytest.raises(InvalidTransitionError):
        VideoStateMachine.transition("vid001", VideoStatus.DISCOVERED, VideoStatus.TRANSCRIBED)


def test_video_can_transition_true() -> None:
    assert VideoStateMachine.can_transition(VideoStatus.DISCOVERED, VideoStatus.TRIAGE_METADATA_PASSED) is True


def test_video_can_transition_false() -> None:
    assert VideoStateMachine.can_transition(VideoStatus.DISCOVERED, VideoStatus.TRANSCRIBED) is False


def test_video_all_statuses_have_transitions() -> None:
    all_statuses = set(VideoStatus)
    missing = all_statuses - set(VIDEO_TRANSITIONS.keys())
    assert not missing, f"Status sem transições definidas: {missing}"


# ---------------------------------------------------------------------------
# ClipStateMachine
# ---------------------------------------------------------------------------


def test_clip_valid_transition_identified_to_editing() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.IDENTIFIED, ClipStatus.EDITING)


def test_clip_valid_transition_editing_to_edited() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.EDITING, ClipStatus.EDITED)


def test_clip_valid_transition_editing_retry() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.EDITING, ClipStatus.IDENTIFIED)


def test_clip_valid_transition_to_youtube() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.METADATA_READY, ClipStatus.SCHEDULED_YOUTUBE)


def test_clip_valid_transition_to_tiktok() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.METADATA_READY, ClipStatus.PENDING_TIKTOK_MANUAL)


def test_clip_invalid_transition_raises() -> None:
    with pytest.raises(InvalidTransitionError, match="editing"):
        ClipStateMachine.transition("clip001", ClipStatus.UPLOADED_TIKTOK, ClipStatus.EDITING)


def test_clip_invalid_skip_state() -> None:
    with pytest.raises(InvalidTransitionError):
        ClipStateMachine.transition("clip001", ClipStatus.IDENTIFIED, ClipStatus.UPLOADED_YOUTUBE)


def test_clip_can_transition_true() -> None:
    assert ClipStateMachine.can_transition(ClipStatus.IDENTIFIED, ClipStatus.EDITING) is True


def test_clip_can_transition_false() -> None:
    assert ClipStateMachine.can_transition(ClipStatus.UPLOADED_TIKTOK, ClipStatus.IDENTIFIED) is False


def test_clip_all_statuses_have_transitions() -> None:
    all_statuses = set(ClipStatus)
    missing = all_statuses - set(CLIP_TRANSITIONS.keys())
    assert not missing, f"Status sem transições definidas: {missing}"


# novos status de sync YouTube
def test_clip_scheduled_to_uploaded() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.SCHEDULED_YOUTUBE, ClipStatus.UPLOADED_YOUTUBE)


def test_clip_scheduled_to_rejected() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.SCHEDULED_YOUTUBE, ClipStatus.REJECTED_YOUTUBE)


def test_clip_scheduled_to_deleted() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.SCHEDULED_YOUTUBE, ClipStatus.DELETED_YOUTUBE)


def test_clip_scheduled_to_unscheduled() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.SCHEDULED_YOUTUBE, ClipStatus.UNSCHEDULED_YOUTUBE)


def test_clip_uploaded_to_deleted() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.UPLOADED_YOUTUBE, ClipStatus.DELETED_YOUTUBE)


def test_clip_rejected_can_retry() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.REJECTED_YOUTUBE, ClipStatus.IDENTIFIED)


def test_clip_deleted_can_restart() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.DELETED_YOUTUBE, ClipStatus.IDENTIFIED)


def test_clip_unscheduled_to_scheduled() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.UNSCHEDULED_YOUTUBE, ClipStatus.SCHEDULED_YOUTUBE)


def test_clip_unscheduled_to_metadata_ready() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.UNSCHEDULED_YOUTUBE, ClipStatus.METADATA_READY)


def test_clip_uploading_to_scheduled() -> None:
    ClipStateMachine.transition("clip001", ClipStatus.UPLOADING_YOUTUBE, ClipStatus.SCHEDULED_YOUTUBE)


def test_clip_invalid_uploaded_to_identified() -> None:
    with pytest.raises(InvalidTransitionError):
        ClipStateMachine.transition("clip001", ClipStatus.UPLOADED_YOUTUBE, ClipStatus.IDENTIFIED)


# ---------------------------------------------------------------------------
# PipelineService.transition_* (smoke)
# ---------------------------------------------------------------------------


def test_service_transition_video(tmp_path: Any) -> None:
    from pathlib import Path

    from canal_soberania.config import Settings
    from canal_soberania.db import connect, init_db
    from canal_soberania.services.pipeline_service import PipelineService
    from tests.fakes import InMemoryClipRepository, InMemoryVideoRepository

    SCHEMA = Path(__file__).parent.parent / "schema.sql"
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    conn = connect(db_path)
    service = PipelineService(
        conn=conn,
        settings=Settings(data_dir=tmp_path),
        paths={"data_dir": tmp_path, "db_path": db_path, "schema_path": SCHEMA, "log_dir": tmp_path},
        video_repo=InMemoryVideoRepository(),
        clip_repo=InMemoryClipRepository(),
    )
    service.transition_video("vid001", VideoStatus.DISCOVERED, VideoStatus.TRIAGE_METADATA_PASSED)


def test_service_transition_video_invalid(tmp_path: Any) -> None:
    from pathlib import Path

    from canal_soberania.config import Settings
    from canal_soberania.db import connect, init_db
    from canal_soberania.services.pipeline_service import PipelineService
    from tests.fakes import InMemoryClipRepository, InMemoryVideoRepository

    SCHEMA = Path(__file__).parent.parent / "schema.sql"
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    conn = connect(db_path)
    service = PipelineService(
        conn=conn,
        settings=Settings(data_dir=tmp_path),
        paths={"data_dir": tmp_path, "db_path": db_path, "schema_path": SCHEMA, "log_dir": tmp_path},
        video_repo=InMemoryVideoRepository(),
        clip_repo=InMemoryClipRepository(),
    )
    with pytest.raises(InvalidTransitionError):
        service.transition_video("vid001", VideoStatus.CLIPS_FOUND, VideoStatus.DISCOVERED)


# needed for tmp_path in module-level tests above
from typing import Any
