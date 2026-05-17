"""Event Bus para notificações do pipeline em tempo real.

PipelineService publica eventos; qualquer UI (PySide6, FastAPI/WebSocket)
registra handlers. Thread-safe: os handlers são chamados na thread que
publicou o evento — UIs com event loop próprio (Qt) devem usar bridge.py.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PipelineEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    # tipos canônicos
    STAGE_STARTED = "stage_started"
    STAGE_PROGRESS = "stage_progress"
    STAGE_COMPLETED = "stage_completed"
    STAGE_ERROR = "stage_error"
    ITEM_PROCESSED = "item_processed"


Handler = Callable[[PipelineEvent], None]


class EventBus:
    """Bus simples de pub/sub. Handlers são chamados de forma síncrona."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Handler) -> None:
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        with self._lock:
            handlers = self._handlers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(self, event: PipelineEvent) -> None:
        with self._lock:
            handlers = list(self._handlers.get(event.type, []))
            wildcard = list(self._handlers.get("*", []))
        for h in handlers + wildcard:
            h(event)

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()
