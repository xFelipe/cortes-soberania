"""Bridge entre EventBus (síncrono) e SSE (asyncio)."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncGenerator
from typing import Any

from canal_soberania.core.events import EventBus, PipelineEvent


class SSEBridge:
    """Converte eventos síncronos do EventBus em Server-Sent Events async.

    Thread-safety: EventBus chama `_on_event` de qualquer thread do pipeline.
    Usamos `loop.call_soon_threadsafe` para entregar na fila do asyncio.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._clients: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[PipelineEvent]]] = []
        self._lock = threading.Lock()
        bus.subscribe("*", self._on_event)

    def _on_event(self, event: PipelineEvent) -> None:
        with self._lock:
            snapshot = list(self._clients)
        for loop, q in snapshot:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except (RuntimeError, asyncio.QueueFull):
                pass

    async def stream(self) -> AsyncGenerator[str, None]:
        """Gerador SSE — cada yield é uma mensagem `data: ...\n\n`."""
        loop = asyncio.get_event_loop()
        q: asyncio.Queue[PipelineEvent] = asyncio.Queue(maxsize=200)

        with self._lock:
            self._clients.append((loop, q))

        try:
            yield _heartbeat()  # primeiro evento ao conectar
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield _format_event(event)
                except TimeoutError:
                    yield _heartbeat()  # keep-alive
        finally:
            with self._lock:
                try:
                    self._clients.remove((loop, q))
                except ValueError:
                    pass


def _format_event(event: PipelineEvent) -> str:
    payload: dict[str, Any] = {"type": event.type, "payload": event.payload}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _heartbeat() -> str:
    return ": heartbeat\n\n"
