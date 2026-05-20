"""Testes para /stages, /pipeline, /stats, /inbox e /health."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


# ── health ────────────────────────────────────────────────────────────────────

def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── stages ────────────────────────────────────────────────────────────────────

def test_run_stage_discover(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.post("/stages/discover/run", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "started"
    assert body["stage"] == "discover"
    mock_service.reset_cancel.assert_called_once()


def test_run_stage_auto(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.post("/stages/auto/run", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["stage"] == "auto"


def test_run_stage_invalid(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.post("/stages/nope/run", headers=auth_headers)
    assert r.status_code == 404


def test_run_stage_no_auth(client: TestClient) -> None:
    r = client.post("/stages/discover/run")
    assert r.status_code == 401


@pytest.mark.parametrize(
    "name",
    [
        "triage_metadata",
        "triage_caption",
        "download",
        "transcribe",
        "triage_transcript",
        "find_clips",
        "edit",
        "thumbnail",
        "generate_metadata",
        "upload_youtube",
        "upload_tiktok",
        "sync_youtube",
    ],
)
def test_run_all_known_stages(
    client: TestClient, auth_headers: dict[str, str], name: str
) -> None:
    r = client.post(f"/stages/{name}/run", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["stage"] == name


# ── pipeline control ──────────────────────────────────────────────────────────

def test_cancel_pipeline(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.post("/pipeline/cancel", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelling"
    mock_service.cancel.assert_called_once()


def test_reset_stuck(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.reset_stuck_videos.return_value = 2
    mock_service.reset_stuck_clips.return_value = 1
    r = client.post("/pipeline/reset", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["reset_videos"] == 2
    assert body["reset_clips"] == 1


def test_reset_stuck_no_auth(client: TestClient) -> None:
    r = client.post("/pipeline/reset")
    assert r.status_code == 401


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_summary(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/stats/summary", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert data.get("discovered") == 3


def test_stats_costs(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/stats/costs", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total_usd"] == pytest.approx(1.23)


def test_stats_costs_detail_empty(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/stats/costs/detail", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_stats_costs_detail_with_data(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    from tests.api.conftest import _TOKEN  # noqa: PLC0415

    conn = client.app.state.conn  # type: ignore[attr-defined]
    conn.execute(
        "INSERT INTO api_costs VALUES (?,?,?,?,?,?,?)",
        ("2024-01-15", "anthropic", "claude-haiku-4-5", 100, 50, 1, 0.001),
    )
    conn.commit()
    r = client.get("/stats/costs/detail", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["provider"] == "anthropic"


def test_stats_no_auth(client: TestClient) -> None:
    r = client.get("/stats/summary")
    assert r.status_code == 401


# ── inbox ─────────────────────────────────────────────────────────────────────

def test_inbox(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/inbox", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == len(body["items"])


def test_inbox_contains_clip_priority_1(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/inbox", headers=auth_headers)
    items = r.json()["items"]
    clip_items = [i for i in items if i["type"] == "clip"]
    assert len(clip_items) >= 1
    assert all(i["priority"] == 1 for i in clip_items)


def test_inbox_contains_video_priority_2(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/inbox", headers=auth_headers)
    items = r.json()["items"]
    video_items = [i for i in items if i["type"] == "video"]
    priorities = {i["priority"] for i in video_items}
    assert 2 in priorities


def test_inbox_no_auth(client: TestClient) -> None:
    r = client.get("/inbox")
    assert r.status_code == 401


# ── discover adhoc ────────────────────────────────────────────────────────────

def test_discover_adhoc_no_api_key(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service._settings.youtube_api_key = ""
    r = client.post(
        "/discover/adhoc",
        json={"channel_url_or_handle": "@teste"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_discover_adhoc_started(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service._settings.youtube_api_key = "fake-key"
    mock_service.discover_adhoc.return_value = 5
    r = client.post(
        "/discover/adhoc",
        json={"channel_url_or_handle": "@teste", "persist": True},
        headers=auth_headers,
    )
    assert r.status_code == 202
    assert r.json()["status"] == "started"
    assert r.json()["handle"] == "@teste"


def test_discover_adhoc_no_auth(client: TestClient) -> None:
    r = client.post("/discover/adhoc", json={"channel_url_or_handle": "@teste"})
    assert r.status_code == 401


# ── stats by-canal / throughput ───────────────────────────────────────────────

def test_stats_by_canal_empty(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/stats/by-canal", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_stats_throughput_empty(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/stats/throughput", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_stats_by_canal_with_data(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    conn = client.app.state.conn  # type: ignore[attr-defined]
    conn.execute(
        """CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY, canal_id TEXT NOT NULL, title TEXT NOT NULL,
            published_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'discovered',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS clips (
            clip_id TEXT PRIMARY KEY, video_id TEXT NOT NULL,
            start_s REAL NOT NULL, end_s REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'identified',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "INSERT OR IGNORE INTO videos VALUES ('vid1','canal-a','T','2024-01-01T00:00:00Z','clips_found','2024-01-01','2024-01-01')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO clips VALUES ('vid1_10_70','vid1',10,70,'uploaded_youtube','2024-01-01','2024-01-01')"
    )
    conn.commit()
    r = client.get("/stats/by-canal", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["canal_id"] == "canal-a"
    assert rows[0]["clips_publicados"] == 1


def test_stats_by_canal_no_auth(client: TestClient) -> None:
    r = client.get("/stats/by-canal")
    assert r.status_code == 401


def test_stats_throughput_no_auth(client: TestClient) -> None:
    r = client.get("/stats/throughput")
    assert r.status_code == 401


# ── pipeline loop pause / resume ──────────────────────────────────────────────

def test_pause_loop(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.post("/pipeline/pause", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["paused"] is True
    mock_service.pause_loop.assert_called_once()


def test_resume_loop(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.post("/pipeline/resume", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["paused"] is False
    mock_service.resume_loop.assert_called_once()


def test_loop_state_not_paused(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.is_loop_paused.return_value = False
    r = client.get("/pipeline/loop-state", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["paused"] is False


def test_loop_state_paused(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.is_loop_paused.return_value = True
    r = client.get("/pipeline/loop-state", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["paused"] is True


def test_pause_loop_no_auth(client: TestClient) -> None:
    r = client.post("/pipeline/pause")
    assert r.status_code == 401


def test_resume_loop_no_auth(client: TestClient) -> None:
    r = client.post("/pipeline/resume")
    assert r.status_code == 401


def test_loop_state_no_auth(client: TestClient) -> None:
    r = client.get("/pipeline/loop-state")
    assert r.status_code == 401
