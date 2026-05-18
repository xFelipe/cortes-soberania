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
    VideoStateMachine.transition("vid001", "discovered", "triage_metadata_passed")


def test_video_valid_transition_discovered_to_rejected() -> None:
    VideoStateMachine.transition("vid001", "discovered", "triage_metadata_rejected")


def test_video_valid_transition_to_downloading() -> None:
    VideoStateMachine.transition("vid001", "triage_caption_passed", "downloading")


def test_video_valid_transition_downloading_retry() -> None:
    VideoStateMachine.transition("vid001", "downloading", "discovered")


def test_video_valid_transition_to_clips_found() -> None:
    VideoStateMachine.transition("vid001", "finding_clips", "clips_found")


def test_video_invalid_transition_raises() -> None:
    with pytest.raises(InvalidTransitionError, match="discovered"):
        VideoStateMachine.transition("vid001", "clips_found", "discovered")


def test_video_invalid_transition_skip_state() -> None:
    with pytest.raises(InvalidTransitionError):
        VideoStateMachine.transition("vid001", "discovered", "transcribed")


def test_video_can_transition_true() -> None:
    assert VideoStateMachine.can_transition("discovered", "triage_metadata_passed") is True


def test_video_can_transition_false() -> None:
    assert VideoStateMachine.can_transition("discovered", "uploaded_youtube") is False  # type: ignore[arg-type]


def test_video_all_statuses_have_transitions() -> None:
    from canal_soberania.models import VideoStatus
    import typing
    all_statuses = set(typing.get_args(VideoStatus))
    missing = all_statuses - set(VIDEO_TRANSITIONS.keys())
    assert not missing, f"Status sem transições definidas: {missing}"


# ---------------------------------------------------------------------------
# ClipStateMachine
# ---------------------------------------------------------------------------


def test_clip_valid_transition_identified_to_editing() -> None:
    ClipStateMachine.transition("clip001", "identified", "editing")


def test_clip_valid_transition_editing_to_edited() -> None:
    ClipStateMachine.transition("clip001", "editing", "edited")


def test_clip_valid_transition_editing_retry() -> None:
    ClipStateMachine.transition("clip001", "editing", "identified")


def test_clip_valid_transition_to_youtube() -> None:
    ClipStateMachine.transition("clip001", "metadata_ready", "scheduled_youtube")


def test_clip_valid_transition_to_tiktok() -> None:
    ClipStateMachine.transition("clip001", "metadata_ready", "pending_tiktok_manual")


def test_clip_invalid_transition_raises() -> None:
    with pytest.raises(InvalidTransitionError, match="editing"):
        ClipStateMachine.transition("clip001", "uploaded_tiktok", "editing")


def test_clip_invalid_skip_state() -> None:
    with pytest.raises(InvalidTransitionError):
        ClipStateMachine.transition("clip001", "identified", "uploaded_youtube")


def test_clip_can_transition_true() -> None:
    assert ClipStateMachine.can_transition("identified", "editing") is True


def test_clip_can_transition_false() -> None:
    assert ClipStateMachine.can_transition("uploaded_tiktok", "identified") is False


def test_clip_all_statuses_have_transitions() -> None:
    import typing
    all_statuses = set(typing.get_args(ClipStatus))
    missing = all_statuses - set(CLIP_TRANSITIONS.keys())
    assert not missing, f"Status sem transições definidas: {missing}"


# novos status de sync YouTube
def test_clip_scheduled_to_uploaded() -> None:
    ClipStateMachine.transition("clip001", "scheduled_youtube", "uploaded_youtube")


def test_clip_scheduled_to_rejected() -> None:
    ClipStateMachine.transition("clip001", "scheduled_youtube", "rejected_youtube")


def test_clip_scheduled_to_deleted() -> None:
    ClipStateMachine.transition("clip001", "scheduled_youtube", "deleted_youtube")


def test_clip_scheduled_to_unscheduled() -> None:
    ClipStateMachine.transition("clip001", "scheduled_youtube", "unscheduled_youtube")


def test_clip_uploaded_to_deleted() -> None:
    ClipStateMachine.transition("clip001", "uploaded_youtube", "deleted_youtube")


def test_clip_rejected_can_retry() -> None:
    ClipStateMachine.transition("clip001", "rejected_youtube", "identified")


def test_clip_deleted_can_restart() -> None:
    ClipStateMachine.transition("clip001", "deleted_youtube", "identified")


def test_clip_unscheduled_to_scheduled() -> None:
    ClipStateMachine.transition("clip001", "unscheduled_youtube", "scheduled_youtube")


def test_clip_unscheduled_to_metadata_ready() -> None:
    ClipStateMachine.transition("clip001", "unscheduled_youtube", "metadata_ready")


def test_clip_uploading_to_scheduled() -> None:
    ClipStateMachine.transition("clip001", "uploading_youtube", "scheduled_youtube")


def test_clip_invalid_uploaded_to_identified() -> None:
    with pytest.raises(InvalidTransitionError):
        ClipStateMachine.transition("clip001", "uploaded_youtube", "identified")


# ---------------------------------------------------------------------------
# PipelineService.transition_* (smoke)
# ---------------------------------------------------------------------------


def test_service_transition_video(tmp_path: Any) -> None:
    from pathlib import Path
    import sqlite3
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
    service.transition_video("vid001", "discovered", "triage_metadata_passed")


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
        service.transition_video("vid001", "clips_found", "discovered")


# needed for tmp_path in module-level tests above
from typing import Any
