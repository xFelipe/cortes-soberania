"""Protocolo Stage (Command pattern) — cada etapa do pipeline implementa esta interface."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from canal_soberania.config import Settings


@dataclass
class JobContext:
    """Contexto passado a cada stage na execução."""
    conn: sqlite3.Connection
    settings: Settings
    paths: dict[str, Path]
    dry_run: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageResult:
    success: bool
    items_processed: int = 0
    error: Exception | None = None


@runtime_checkable
class Stage(Protocol):
    """Protocolo que cada stage deve implementar para ser cancellável e retriável."""

    @property
    def name(self) -> str: ...

    def execute(self, ctx: JobContext) -> StageResult: ...

    def can_retry(self, error: Exception) -> bool: ...

    def rollback(self, ctx: JobContext) -> None: ...
