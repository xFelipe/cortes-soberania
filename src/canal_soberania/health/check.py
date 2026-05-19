"""Verificações de saúde do pipeline."""

from __future__ import annotations

import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from canal_soberania.config import Settings
from canal_soberania.db import status_summary
from canal_soberania.logger import logger

# itens num mesmo status além desse limite disparam alerta
_STUCK_THRESHOLD_DEFAULT = 50
# tempo máximo sem iteração do loop antes de considerar parado (segundos)
_LOOP_IDLE_THRESHOLD_S = 7200   # 2 horas
# espaço mínimo em disco (bytes)
_MIN_DISK_FREE_BYTES = 2 * 1024 ** 3   # 2 GiB


@dataclass
class HealthResult:
    ok: bool
    db_ok: bool = True
    disk_free_gb: float = 0.0
    disk_ok: bool = True
    stuck_items: list[tuple[str, int]] = field(default_factory=list)
    loop_idle_hours: float | None = None
    loop_ok: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"Disco livre: {self.disk_free_gb:.1f} GB"]
        if self.stuck_items:
            stuck_str = ", ".join(f"{s}: {n}" for s, n in self.stuck_items)
            parts.append(f"Presos: {stuck_str}")
        if self.loop_idle_hours is not None:
            parts.append(f"Loop idle: {self.loop_idle_hours:.1f}h")
        if self.warnings:
            parts.append(f"Avisos: {'; '.join(self.warnings)}")
        if self.errors:
            parts.append(f"Erros: {'; '.join(self.errors)}")
        status = "OK" if self.ok else "FALHA"
        return f"[{status}] {' | '.join(parts)}"


def run_health_check(
    conn: sqlite3.Connection,
    settings: Settings,
    paths: dict[str, Path],
    loop_heartbeat_file: Path | None = None,
    stuck_threshold: int = _STUCK_THRESHOLD_DEFAULT,
) -> HealthResult:
    """Executa todas as verificações e retorna HealthResult."""
    result = HealthResult(ok=True)

    # --- DB ping ---
    try:
        conn.execute("SELECT 1")
    except Exception as exc:
        result.db_ok = False
        result.errors.append(f"DB inacessível: {exc}")
        result.ok = False

    # --- Disco ---
    try:
        usage = shutil.disk_usage(paths["data_dir"])
        result.disk_free_gb = usage.free / 1024 ** 3
        if usage.free < _MIN_DISK_FREE_BYTES:
            result.disk_ok = False
            result.warnings.append(f"Pouco espaço em disco: {result.disk_free_gb:.1f} GB")
    except Exception as exc:
        result.warnings.append(f"Falha ao verificar disco: {exc}")

    # --- Itens presos ---
    if result.db_ok:
        try:
            summary = status_summary(conn)
            result.stuck_items = [
                (status, count)
                for status, count in summary.items()
                if count > stuck_threshold
            ]
            if result.stuck_items:
                result.warnings.append(
                    f"{len(result.stuck_items)} status(es) com >{stuck_threshold} itens"
                )
        except Exception as exc:
            result.warnings.append(f"Falha ao verificar itens presos: {exc}")

    # --- Loop ativo ---
    if loop_heartbeat_file and loop_heartbeat_file.exists():
        try:
            mtime = loop_heartbeat_file.stat().st_mtime
            idle_s = time.time() - mtime
            result.loop_idle_hours = idle_s / 3600
            if idle_s > _LOOP_IDLE_THRESHOLD_S:
                result.loop_ok = False
                result.ok = False
                result.errors.append(
                    f"Loop parado há {result.loop_idle_hours:.1f}h"
                )
        except Exception as exc:
            result.warnings.append(f"Falha ao verificar heartbeat: {exc}")

    if result.warnings and result.ok:
        # Avisos não derrubam o ok — mas logamos
        pass

    logger.info("Healthcheck: {}", result.summary())
    return result
