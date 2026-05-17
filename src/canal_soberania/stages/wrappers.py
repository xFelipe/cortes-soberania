"""Wrappers que adaptam os stages existentes ao protocolo Stage (Command pattern).

Cada wrapper delega ao run() original e implementa can_retry/rollback sem
alterar os módulos de stage existentes (preserva os 181 testes anteriores).
"""

from __future__ import annotations

import sqlite3
from typing import Callable

from canal_soberania.core.stage import JobContext, Stage, StageResult


def _is_network_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("connection", "timeout", "network", "socket", "urlerror", "http"))


class _FuncStage:
    """Adapta qualquer run(conn, dry_run) ao protocolo Stage."""

    def __init__(
        self,
        stage_name: str,
        run_fn: Callable[..., None],
        retryable_on_network: bool = True,
    ) -> None:
        self._name = stage_name
        self._run_fn = run_fn
        self._retryable = retryable_on_network

    @property
    def name(self) -> str:
        return self._name

    def execute(self, ctx: JobContext) -> StageResult:
        try:
            self._run_fn(conn=ctx.conn, dry_run=ctx.dry_run)
            return StageResult(success=True)
        except Exception as exc:
            return StageResult(success=False, error=exc)

    def can_retry(self, error: Exception) -> bool:
        return self._retryable and _is_network_error(error)

    def rollback(self, ctx: JobContext) -> None:
        pass  # stages são idempotentes; rollback é rerun


def _make(name: str, module_path: str, retryable: bool = True) -> _FuncStage:
    import importlib
    mod = importlib.import_module(module_path)
    return _FuncStage(name, mod.run, retryable)


def get_stage(name: str) -> Stage:
    """Retorna a instância de Stage pelo nome canônico."""
    registry: dict[str, Stage] = {
        "discover":           _make("discover",           "canal_soberania.stages.discover"),
        "triage_metadata":    _make("triage_metadata",    "canal_soberania.stages.triage_metadata"),
        "triage_caption":     _make("triage_caption",     "canal_soberania.stages.triage_caption"),
        "triage_transcript":  _make("triage_transcript",  "canal_soberania.stages.triage_transcript"),
        "download":           _make("download",           "canal_soberania.stages.download"),
        "transcribe":         _make("transcribe",         "canal_soberania.stages.transcribe"),
        "find_clips":         _make("find_clips",         "canal_soberania.stages.find_clips"),
        "edit":               _make("edit",               "canal_soberania.stages.edit"),
        "thumbnail":          _make("thumbnail",          "canal_soberania.stages.thumbnail"),
        "generate_metadata":  _make("generate_metadata",  "canal_soberania.stages.metadata"),
        "upload_youtube":     _make("upload_youtube",     "canal_soberania.stages.upload_youtube"),
        "upload_tiktok":      _make("upload_tiktok",      "canal_soberania.stages.upload_tiktok"),
    }
    if name not in registry:
        raise KeyError(f"Stage desconhecido: {name!r}")
    return registry[name]
