"""Testes para canal_soberania.health.check."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.config import Settings
from canal_soberania.health.check import HealthResult, run_health_check


def _make_conn(summary: dict[str, int] | None = None) -> MagicMock:
    conn = MagicMock()
    conn.execute.return_value = None
    if summary is not None:
        with patch(
            "canal_soberania.health.check.status_summary",
            return_value=summary,
        ):
            pass
    return conn


@pytest.fixture()
def settings() -> Settings:
    return Settings()


@pytest.fixture()
def paths(tmp_path: Path) -> dict[str, Path]:
    (tmp_path / "data").mkdir()
    return {"data_dir": tmp_path / "data"}


def test_health_result_summary_ok() -> None:
    r = HealthResult(ok=True, disk_free_gb=50.0)
    assert "[OK]" in r.summary()
    assert "50.0" in r.summary()


def test_health_result_summary_fail() -> None:
    r = HealthResult(ok=False, errors=["DB inacessível: X"])
    assert "[FALHA]" in r.summary()


def test_run_health_check_ok(settings: Settings, paths: dict[str, Path]) -> None:
    conn = MagicMock()
    with (
        patch("canal_soberania.health.check.status_summary", return_value={}),
        patch("shutil.disk_usage") as mock_du,
    ):
        mock_du.return_value = MagicMock(free=100 * 1024 ** 3)
        result = run_health_check(conn, settings, paths)

    assert result.ok is True
    assert result.db_ok is True
    assert result.disk_free_gb == pytest.approx(100.0)
    assert result.stuck_items == []


def test_run_health_check_db_failure(settings: Settings, paths: dict[str, Path]) -> None:
    conn = MagicMock()
    conn.execute.side_effect = Exception("DB error")

    with patch("shutil.disk_usage") as mock_du:
        mock_du.return_value = MagicMock(free=100 * 1024 ** 3)
        result = run_health_check(conn, settings, paths)

    assert result.ok is False
    assert result.db_ok is False
    assert any("DB" in e for e in result.errors)


def test_run_health_check_stuck_items_are_warnings(settings: Settings, paths: dict[str, Path]) -> None:
    conn = MagicMock()
    stuck_summary = {"downloading": 200, "discovered": 5}

    with (
        patch("canal_soberania.health.check.status_summary", return_value=stuck_summary),
        patch("shutil.disk_usage") as mock_du,
    ):
        mock_du.return_value = MagicMock(free=100 * 1024 ** 3)
        result = run_health_check(conn, settings, paths, stuck_threshold=50)

    assert result.ok is True  # presos são warnings, não erros fatais
    assert len(result.stuck_items) == 1
    assert result.stuck_items[0] == ("downloading", 200)
    assert result.warnings


def test_run_health_check_loop_ok(
    settings: Settings, paths: dict[str, Path], tmp_path: Path
) -> None:
    heartbeat = tmp_path / ".pipeline_heartbeat"
    heartbeat.touch()

    conn = MagicMock()
    with (
        patch("canal_soberania.health.check.status_summary", return_value={}),
        patch("shutil.disk_usage") as mock_du,
    ):
        mock_du.return_value = MagicMock(free=100 * 1024 ** 3)
        result = run_health_check(conn, settings, paths, loop_heartbeat_file=heartbeat)

    assert result.loop_ok is True
    assert result.ok is True


def test_run_health_check_loop_stuck(
    settings: Settings, paths: dict[str, Path], tmp_path: Path
) -> None:
    heartbeat = tmp_path / ".pipeline_heartbeat"
    heartbeat.touch()
    # Simula heartbeat antigo (3 horas atrás)
    old_time = time.time() - 3 * 3600
    import os
    os.utime(heartbeat, (old_time, old_time))

    conn = MagicMock()
    with (
        patch("canal_soberania.health.check.status_summary", return_value={}),
        patch("shutil.disk_usage") as mock_du,
    ):
        mock_du.return_value = MagicMock(free=100 * 1024 ** 3)
        result = run_health_check(conn, settings, paths, loop_heartbeat_file=heartbeat)

    assert result.loop_ok is False
    assert result.ok is False
    assert result.loop_idle_hours is not None
    assert result.loop_idle_hours > 2.9


def test_run_health_check_low_disk(settings: Settings, paths: dict[str, Path]) -> None:
    conn = MagicMock()
    with (
        patch("canal_soberania.health.check.status_summary", return_value={}),
        patch("shutil.disk_usage") as mock_du,
    ):
        mock_du.return_value = MagicMock(free=500 * 1024 ** 2)  # 500 MB
        result = run_health_check(conn, settings, paths)

    assert result.disk_ok is False
    assert result.warnings
