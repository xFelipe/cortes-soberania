"""Testes para db.py."""

import sqlite3
from pathlib import Path

import pytest

from canal_soberania.db import (
    connect,
    get_clips_by_status,
    get_videos_by_status,
    init_db,
    insert_clip,
    insert_triage_result,
    insert_video,
    record_api_cost,
    status_summary,
    update_video_status,
)
from canal_soberania.models import Clip, TriageResult, Video

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


def _make_video(**kwargs: object) -> Video:
    defaults: dict[str, object] = {
        "video_id": "dQw4w9WgXcQ",
        "canal_id": "flow_podcast",
        "title": "Título",
        "published_at": "2024-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    return Video.model_validate(defaults)


def test_init_db_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "double.db"
    init_db(db_path, SCHEMA)
    init_db(db_path, SCHEMA)  # não deve explodir


def test_insert_and_get_video(db: sqlite3.Connection) -> None:
    v = _make_video()
    with db:
        insert_video(db, v)
    result = get_videos_by_status(db, "discovered")
    assert len(result) == 1
    assert result[0].video_id == "dQw4w9WgXcQ"
    assert result[0].tags == []


def test_insert_video_with_tags(db: sqlite3.Connection) -> None:
    v = _make_video(tags=["geopolitica", "soberania"])
    with db:
        insert_video(db, v)
    result = get_videos_by_status(db, "discovered")
    assert result[0].tags == ["geopolitica", "soberania"]


def test_insert_video_idempotent(db: sqlite3.Connection) -> None:
    v = _make_video()
    with db:
        insert_video(db, v)
        insert_video(db, v)  # INSERT OR IGNORE — não deve explodir
    result = get_videos_by_status(db, "discovered")
    assert len(result) == 1


def test_update_video_status(db: sqlite3.Connection) -> None:
    v = _make_video()
    with db:
        insert_video(db, v)
        update_video_status(db, "dQw4w9WgXcQ", "triage_metadata_passed")
    result = get_videos_by_status(db, "triage_metadata_passed")
    assert len(result) == 1


def test_insert_triage_result(db: sqlite3.Connection) -> None:
    v = _make_video()
    with db:
        insert_video(db, v)
        result = TriageResult(
            video_id="dQw4w9WgXcQ",
            stage="metadata",
            score=7,
            is_relevant=True,
            themes_detected=["geopolitica_brics"],
            rationale="Foco em soberania",
            model_used="claude-haiku-4-5-20251001",
            tokens_in=500,
            tokens_out=80,
            cost_usd=0.0009,
        )
        insert_triage_result(db, result)
    row = db.execute("SELECT * FROM triage_results WHERE video_id = ?", ("dQw4w9WgXcQ",)).fetchone()
    assert row is not None
    assert row["score"] == 7
    assert row["is_relevant"] == 1


def test_insert_clip(db: sqlite3.Connection) -> None:
    v = _make_video()
    c = Clip(
        clip_id="dQw4w9WgXcQ_30_90",
        video_id="dQw4w9WgXcQ",
        start_s=30.0,
        end_s=90.0,
    )
    with db:
        insert_video(db, v)
        insert_clip(db, c)
    clips = get_clips_by_status(db, "identified")
    assert len(clips) == 1
    assert clips[0].clip_id == "dQw4w9WgXcQ_30_90"


def test_record_api_cost(db: sqlite3.Connection) -> None:
    with db:
        record_api_cost(db, "anthropic", "claude-haiku-4-5-20251001", 1000, 200, 0.002)
        record_api_cost(db, "anthropic", "claude-haiku-4-5-20251001", 500, 100, 0.001)
    row = db.execute(
        "SELECT tokens_in, requests, cost_usd FROM api_costs WHERE provider = 'anthropic'"
    ).fetchone()
    assert row["tokens_in"] == 1500
    assert row["requests"] == 2
    assert row["cost_usd"] == pytest.approx(0.003)


def test_status_summary_empty(db: sqlite3.Connection) -> None:
    assert status_summary(db) == {}
