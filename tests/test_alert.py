"""Testes para canal_soberania.alert."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.alert import _send_telegram, check_stuck
from canal_soberania.db import connect, init_db

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


# ---------------------------------------------------------------------------
# check_stuck
# ---------------------------------------------------------------------------


def test_check_stuck_empty_db(db: sqlite3.Connection) -> None:
    result = check_stuck(db, threshold=1)
    assert result == []


def test_check_stuck_below_threshold(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO videos (video_id, canal_id, title, published_at, status) VALUES (?,?,?,?,?)",
        ("vid00000001", "UC1", "T", "2025-01-01", "discovered"),
    )
    db.commit()
    result = check_stuck(db, threshold=5)
    assert result == []


def test_check_stuck_above_threshold(db: sqlite3.Connection) -> None:
    for i in range(3):
        db.execute(
            "INSERT INTO videos (video_id, canal_id, title, published_at, status) VALUES (?,?,?,?,?)",
            (f"vid{i:08d}", "UC1", f"T{i}", "2025-01-01", "downloading"),
        )
    db.commit()
    result = check_stuck(db, threshold=2)
    assert len(result) == 1
    assert result[0][0] == "downloading"
    assert result[0][1] == 3


def test_check_stuck_sends_telegram_on_stuck(db: sqlite3.Connection) -> None:
    for i in range(3):
        db.execute(
            "INSERT INTO videos (video_id, canal_id, title, published_at, status) VALUES (?,?,?,?,?)",
            (f"vid{i:08d}", "UC1", f"T{i}", "2025-01-01", "transcribing"),
        )
    db.commit()

    with patch("canal_soberania.alert._send_telegram", return_value=True) as mock_tg:
        result = check_stuck(db, threshold=2, bot_token="tok", chat_id="123")

    assert result[0][0] == "transcribing"
    mock_tg.assert_called_once()
    _, args, _ = mock_tg.mock_calls[0]
    assert "tok" == args[0]
    assert "123" == args[1]
    assert "transcribing" in args[2]


def test_check_stuck_telegram_failure_logged(db: sqlite3.Connection) -> None:
    for i in range(3):
        db.execute(
            "INSERT INTO videos (video_id, canal_id, title, published_at, status) VALUES (?,?,?,?,?)",
            (f"vid{i:08d}", "UC1", f"T{i}", "2025-01-01", "editing"),
        )
    db.commit()

    with patch("canal_soberania.alert._send_telegram", return_value=False):
        result = check_stuck(db, threshold=2, bot_token="tok", chat_id="123")

    assert result[0][0] == "editing"


# ---------------------------------------------------------------------------
# _send_telegram
# ---------------------------------------------------------------------------


def test_send_telegram_success() -> None:
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _send_telegram("tok", "123", "hello")

    assert result is True


def test_send_telegram_non_200() -> None:
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 401

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _send_telegram("tok", "123", "hello")

    assert result is False


def test_send_telegram_network_error() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        result = _send_telegram("tok", "123", "hello")

    assert result is False
