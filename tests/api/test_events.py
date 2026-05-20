"""Testes para SSEBridge e endpoint GET /events."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from canal_soberania.api.app import create_app
from canal_soberania.api.sse import SSEBridge, _format_event, _heartbeat
from canal_soberania.core.events import EventBus, PipelineEvent


# ---------------------------------------------------------------------------
# Helpers unitários
# ---------------------------------------------------------------------------


def test_heartbeat_format() -> None:
    assert _heartbeat() == ": heartbeat\n\n"


def test_format_event_structure() -> None:
    event = PipelineEvent("stage_started", {"stage": "download"})
    msg = _format_event(event)
    assert msg.startswith("data: ")
    assert msg.endswith("\n\n")
    payload = json.loads(msg[len("data: "):-2])
    assert payload["type"] == "stage_started"
    assert payload["payload"] == {"stage": "download"}


def test_format_event_unicode() -> None:
    event = PipelineEvent("test", {"msg": "ação"})
    msg = _format_event(event)
    payload = json.loads(msg[len("data: "):-2])
    assert payload["payload"]["msg"] == "ação"


# ---------------------------------------------------------------------------
# SSEBridge — unit
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_bridge_yields_heartbeat_on_connect() -> None:
    bus = EventBus()
    bridge = SSEBridge(bus)
    gen = bridge.stream()
    first = await asyncio.wait_for(anext(gen), timeout=2.0)
    assert first == ": heartbeat\n\n"
    await gen.aclose()


@pytest.mark.anyio
async def test_bridge_delivers_event() -> None:
    bus = EventBus()
    bridge = SSEBridge(bus)
    gen = bridge.stream()

    # Consume heartbeat
    await asyncio.wait_for(anext(gen), timeout=2.0)

    # Publish an event from a "background thread" (actually same thread here)
    event = PipelineEvent("video_approved", {"video_id": "abc123"})
    bus.publish(event)

    msg = await asyncio.wait_for(anext(gen), timeout=2.0)
    payload = json.loads(msg[len("data: "):-2])
    assert payload["type"] == "video_approved"
    assert payload["payload"]["video_id"] == "abc123"
    await gen.aclose()


@pytest.mark.anyio
async def test_bridge_removes_client_on_close() -> None:
    bus = EventBus()
    bridge = SSEBridge(bus)
    gen = bridge.stream()
    await asyncio.wait_for(anext(gen), timeout=2.0)

    assert len(bridge._clients) == 1
    await gen.aclose()
    assert len(bridge._clients) == 0


@pytest.mark.anyio
async def test_on_event_skips_closed_loop() -> None:
    """_on_event deve silenciar RuntimeError de loop fechado."""
    bus = EventBus()
    bridge = SSEBridge(bus)

    # Criar cliente com loop fechado
    closed_loop = asyncio.new_event_loop()
    closed_loop.close()
    q: asyncio.Queue[PipelineEvent] = asyncio.Queue()
    bridge._clients.append((closed_loop, q))  # type: ignore[arg-type]

    # Publicar não deve levantar exceção
    bus.publish(PipelineEvent("test", {}))


# ---------------------------------------------------------------------------
# Endpoint GET /events
# ---------------------------------------------------------------------------


def test_events_endpoint_no_auth(client: TestClient) -> None:
    with client.stream("GET", "/events") as r:
        assert r.status_code == 401


@pytest.mark.anyio
async def test_events_endpoint_returns_sse_response() -> None:
    """Verifica que stream_events retorna StreamingResponse com media-type correto.

    httpx.ASGITransport coleta todos os chunks antes de retornar, o que bloqueia
    com SSE infinito.  Testamos a função do endpoint diretamente, sem HTTP.
    """
    from canal_soberania.api.routers.events import stream_events

    bus = EventBus()
    bridge = SSEBridge(bus)

    response = await stream_events(bridge=bridge, _=None)

    assert response.media_type == "text/event-stream"
    # StreamingResponse stores custom headers in raw_headers; check via MutableHeaders
    header_names = {k.lower() for k, _ in response.raw_headers}
    assert b"cache-control" in header_names or "cache-control" in header_names
