"""Testes para EventBus e integração com PipelineService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from canal_soberania.core.events import EventBus, PipelineEvent

# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


def test_subscribe_and_publish() -> None:
    bus = EventBus()
    received: list[PipelineEvent] = []
    bus.subscribe("stage_started", received.append)
    bus.publish(PipelineEvent("stage_started", {"stage": "discover"}))
    assert len(received) == 1
    assert received[0].payload["stage"] == "discover"


def test_wildcard_receives_all_events() -> None:
    bus = EventBus()
    received: list[PipelineEvent] = []
    bus.subscribe("*", received.append)
    bus.publish(PipelineEvent("stage_started"))
    bus.publish(PipelineEvent("stage_completed"))
    assert len(received) == 2


def test_handler_not_called_for_other_type() -> None:
    bus = EventBus()
    received: list[PipelineEvent] = []
    bus.subscribe("stage_started", received.append)
    bus.publish(PipelineEvent("stage_completed"))
    assert len(received) == 0


def test_multiple_handlers_same_type() -> None:
    bus = EventBus()
    calls: list[str] = []
    bus.subscribe("ev", lambda e: calls.append("a"))
    bus.subscribe("ev", lambda e: calls.append("b"))
    bus.publish(PipelineEvent("ev"))
    assert calls == ["a", "b"]


def test_unsubscribe_removes_handler() -> None:
    bus = EventBus()
    received: list[PipelineEvent] = []
    bus.subscribe("ev", received.append)
    bus.unsubscribe("ev", received.append)
    bus.publish(PipelineEvent("ev"))
    assert len(received) == 0


def test_clear_removes_all_handlers() -> None:
    bus = EventBus()
    received: list[PipelineEvent] = []
    bus.subscribe("ev", received.append)
    bus.clear()
    bus.publish(PipelineEvent("ev"))
    assert len(received) == 0


def test_publish_no_handlers_is_noop() -> None:
    bus = EventBus()
    bus.publish(PipelineEvent("orphan_event"))  # não deve lançar


def test_event_payload_defaults_empty() -> None:
    ev = PipelineEvent("test")
    assert ev.payload == {}


def test_event_type_constants() -> None:
    assert PipelineEvent.STAGE_STARTED == "stage_started"
    assert PipelineEvent.STAGE_COMPLETED == "stage_completed"
    assert PipelineEvent.STAGE_ERROR == "stage_error"
    assert PipelineEvent.ITEM_PROCESSED == "item_processed"


# ---------------------------------------------------------------------------
# Integração: PipelineService publica eventos
# ---------------------------------------------------------------------------


@pytest.fixture
def service_with_bus(tmp_path: Path) -> tuple[object, EventBus]:
    from canal_soberania.config import Settings
    from canal_soberania.db import connect, init_db
    from canal_soberania.services.pipeline_service import PipelineService
    from tests.fakes import InMemoryClipRepository, InMemoryVideoRepository

    SCHEMA = Path(__file__).parent.parent / "schema.sql"
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    conn = connect(db_path)
    bus = EventBus()
    svc = PipelineService(
        conn=conn,
        settings=Settings(data_dir=tmp_path),
        paths={"data_dir": tmp_path, "db_path": db_path, "schema_path": SCHEMA, "log_dir": tmp_path},
        video_repo=InMemoryVideoRepository(),
        clip_repo=InMemoryClipRepository(),
        event_bus=bus,
    )
    return svc, bus


def test_service_publishes_stage_started(service_with_bus: tuple) -> None:
    svc, bus = service_with_bus
    received: list[PipelineEvent] = []
    bus.subscribe(PipelineEvent.STAGE_STARTED, received.append)
    with patch("canal_soberania.stages.discover.run"):
        svc.run_discover(dry_run=True)
    assert len(received) == 1
    assert received[0].payload["stage"] == "discover"


def test_service_publishes_stage_completed(service_with_bus: tuple) -> None:
    svc, bus = service_with_bus
    received: list[PipelineEvent] = []
    bus.subscribe(PipelineEvent.STAGE_COMPLETED, received.append)
    with patch("canal_soberania.stages.triage_metadata.run"):
        svc.run_triage_metadata(dry_run=True)
    assert len(received) == 1
    assert received[0].payload["stage"] == "triage_metadata"


def test_service_publishes_stage_error_on_exception(service_with_bus: tuple) -> None:
    svc, bus = service_with_bus
    errors: list[PipelineEvent] = []
    bus.subscribe(PipelineEvent.STAGE_ERROR, errors.append)
    with patch("canal_soberania.stages.download.run", side_effect=RuntimeError("falha de rede")):
        with pytest.raises(RuntimeError):
            svc.run_download(dry_run=True)
    assert len(errors) == 1
    assert "falha de rede" in errors[0].payload["error"]


def test_service_event_bus_property(service_with_bus: tuple) -> None:
    svc, bus = service_with_bus
    assert svc.event_bus is bus
