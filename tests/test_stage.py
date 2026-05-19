"""Testes para o protocolo Stage e wrappers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from canal_soberania.core.stage import JobContext, Stage
from canal_soberania.stages.wrappers import _FuncStage, get_stage

# ---------------------------------------------------------------------------
# Protocolo Stage
# ---------------------------------------------------------------------------


def test_func_stage_satisfies_protocol(tmp_path: Path) -> None:
    stage = _FuncStage("test", lambda **kw: None)
    assert isinstance(stage, Stage)


def test_func_stage_name() -> None:
    stage = _FuncStage("my_stage", lambda **kw: None)
    assert stage.name == "my_stage"


def test_func_stage_execute_success(tmp_path: Path) -> None:
    import sqlite3

    from canal_soberania.config import Settings
    called = []
    stage = _FuncStage("test", lambda **kw: called.append(True))
    ctx = JobContext(
        conn=sqlite3.connect(":memory:"),
        settings=Settings(),
        paths={},
        dry_run=True,
    )
    result = stage.execute(ctx)
    assert result.success is True
    assert result.error is None
    assert called == [True]


def test_func_stage_execute_failure(tmp_path: Path) -> None:
    import sqlite3

    from canal_soberania.config import Settings
    exc = RuntimeError("boom")
    stage = _FuncStage("test", lambda **kw: (_ for _ in ()).throw(exc))
    ctx = JobContext(conn=sqlite3.connect(":memory:"), settings=Settings(), paths={})
    result = stage.execute(ctx)
    assert result.success is False
    assert result.error is exc


def test_func_stage_can_retry_network_error() -> None:
    stage = _FuncStage("test", lambda **kw: None, retryable_on_network=True)
    assert stage.can_retry(ConnectionError("timeout")) is True


def test_func_stage_can_retry_non_network_error() -> None:
    stage = _FuncStage("test", lambda **kw: None, retryable_on_network=True)
    assert stage.can_retry(ValueError("bad value")) is False


def test_func_stage_not_retryable() -> None:
    stage = _FuncStage("test", lambda **kw: None, retryable_on_network=False)
    assert stage.can_retry(ConnectionError("timeout")) is False


def test_func_stage_rollback_is_noop(tmp_path: Path) -> None:
    import sqlite3

    from canal_soberania.config import Settings
    stage = _FuncStage("test", lambda **kw: None)
    ctx = JobContext(conn=sqlite3.connect(":memory:"), settings=Settings(), paths={})
    stage.rollback(ctx)  # não deve lançar


# ---------------------------------------------------------------------------
# get_stage registry
# ---------------------------------------------------------------------------


def test_get_stage_known() -> None:
    stage = get_stage("discover")
    assert stage.name == "discover"


def test_get_stage_all_registered() -> None:
    names = [
        "discover", "triage_metadata", "triage_caption", "triage_transcript",
        "download", "transcribe", "find_clips", "edit",
        "thumbnail", "generate_metadata", "upload_youtube", "upload_tiktok",
    ]
    for name in names:
        stage = get_stage(name)
        assert stage.name == name


def test_get_stage_unknown_raises() -> None:
    with pytest.raises(KeyError, match="nonexistent"):
        get_stage("nonexistent")


# ---------------------------------------------------------------------------
# PipelineService — cancel e run_stage com Stage Protocol
# ---------------------------------------------------------------------------


@pytest.fixture
def svc(tmp_path: Path) -> object:
    from canal_soberania.config import Settings
    from canal_soberania.db import connect, init_db
    from canal_soberania.services.pipeline_service import PipelineService
    from tests.fakes import InMemoryClipRepository, InMemoryVideoRepository

    SCHEMA = Path(__file__).parent.parent / "schema.sql"
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    conn = connect(db_path)
    return PipelineService(
        conn=conn,
        settings=Settings(data_dir=tmp_path),
        paths={"data_dir": tmp_path, "db_path": db_path, "schema_path": SCHEMA, "log_dir": tmp_path},
        video_repo=InMemoryVideoRepository(),
        clip_repo=InMemoryClipRepository(),
    )


def test_cancel_prevents_stage_run(svc: object) -> None:
    svc.cancel()
    assert svc.is_cancelled is True
    with patch("canal_soberania.stages.discover.run") as mock_run:
        svc.run_discover(dry_run=True)
        mock_run.assert_not_called()


def test_reset_cancel_allows_run(svc: object) -> None:
    svc.cancel()
    svc.reset_cancel()
    assert svc.is_cancelled is False
    with patch("canal_soberania.stages.discover.run"):
        svc.run_discover(dry_run=True)  # não deve lançar


def test_cancel_publishes_cancelled_event(svc: object) -> None:
    from canal_soberania.core.events import PipelineEvent
    cancelled: list[PipelineEvent] = []
    svc.event_bus.subscribe("stage_cancelled", cancelled.append)
    svc.cancel()
    with patch("canal_soberania.stages.discover.run"):
        svc.run_discover(dry_run=True)
    assert len(cancelled) == 1
    assert cancelled[0].payload["stage"] == "discover"
