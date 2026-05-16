"""Testes para stages/upload_youtube.py (API mockada)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, Video
from canal_soberania.stages.upload_youtube import (
    _next_publish_slot,
    upload_clip,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def clip(tmp_path: Path) -> Clip:
    mp4 = tmp_path / "clips" / "abc123XYZ01_30_90_vertical.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"fake_video")
    return Clip(
        clip_id="abc123XYZ01_30_90",
        video_id="abc123XYZ01",
        start_s=30.0,
        end_s=90.0,
        hook="Brasil soberania",
        payoff="política industrial",
        tema_soberania="industria_defesa",
        score_viral=8,
        score_relevancia=9,
        clip_path_vertical=str(mp4),
        title="Brasil perde soberania",
        description="Análise detalhada.",
        tags=["soberania", "brasil"],
    )


@pytest.fixture
def clip_in_db(db: sqlite3.Connection, clip: Clip) -> Clip:
    video = Video(
        video_id="abc123XYZ01",
        canal_id="flow_podcast",
        title="Episódio 1",
        published_at="2026-01-01T00:00:00Z",
    )
    insert_video(db, video)
    insert_clip(db, clip)
    return clip


# ---------------------------------------------------------------------------
# _next_publish_slot
# ---------------------------------------------------------------------------


def test_next_publish_slot_returns_future_datetime(db: sqlite3.Connection) -> None:
    slot = _next_publish_slot(db)
    assert isinstance(slot, datetime)
    assert slot > datetime.now(timezone.utc)


def test_next_publish_slot_respects_hours(db: sqlite3.Connection) -> None:
    from datetime import timedelta

    slot = _next_publish_slot(db, publish_hours_brt=[9, 14, 19])
    brt = slot.astimezone(timezone(timedelta(hours=-3)))
    assert brt.hour in [9, 14, 19]


def test_next_publish_slot_avoids_full_days(db: sqlite3.Connection) -> None:
    from datetime import timedelta

    # Insert a placeholder video to satisfy FK constraint
    db.execute(
        "INSERT INTO videos (video_id, canal_id, title, published_at, status) "
        "VALUES ('placeholder01', 'c', 'T', '2026-01-01', 'discovered')"
    )

    # Pre-fill all slots for the next 2 days
    brt = timezone(timedelta(hours=-3))
    now_brt = datetime.now(brt)
    slot_count = 0
    for day_offset in range(2):
        for hour in [9, 14, 19]:
            target = now_brt.date() + timedelta(days=day_offset)
            dt_brt = datetime(target.year, target.month, target.day, hour, tzinfo=brt)
            if dt_brt > now_brt:
                iso = dt_brt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                db.execute(
                    "INSERT INTO clips (clip_id, video_id, start_s, end_s, status, youtube_publish_at) "
                    "VALUES (?, 'placeholder01', 0, 60, 'scheduled_youtube', ?)",
                    (f"fake_{day_offset}_{hour}", iso),
                )
                slot_count += 1
    db.commit()

    slot = _next_publish_slot(db, max_per_day=3, publish_hours_brt=[9, 14, 19])
    assert slot > datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# upload_clip
# ---------------------------------------------------------------------------


def test_upload_clip_dry_run(clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path) -> None:
    result = upload_clip(
        clip=clip_in_db,
        conn=db,
        client_secrets_path=tmp_path / "secrets.json",
        token_path=tmp_path / "token.json",
        dry_run=True,
    )
    assert result is None
    row = db.execute("SELECT status FROM clips WHERE clip_id=?", (clip_in_db.clip_id,)).fetchone()
    assert row["status"] != "scheduled_youtube"


def test_upload_clip_no_vertical_path(db: sqlite3.Connection, tmp_path: Path) -> None:
    clip_no_video = Clip(
        clip_id="novert00001_30_90",
        video_id="novert00001",
        start_s=30.0,
        end_s=90.0,
        hook="hook",
        score_viral=5,
        score_relevancia=5,
    )
    video = Video(
        video_id="novert00001",
        canal_id="canal",
        title="T",
        published_at="2026-01-01T00:00:00Z",
    )
    insert_video(db, video)
    insert_clip(db, clip_no_video)

    result = upload_clip(
        clip=clip_no_video,
        conn=db,
        client_secrets_path=tmp_path / "s.json",
        token_path=tmp_path / "t.json",
    )
    assert result is None


def test_upload_clip_missing_file(db: sqlite3.Connection, tmp_path: Path) -> None:
    clip_bad = Clip(
        clip_id="badclip0001_30_90",
        video_id="badclip0001",
        start_s=30.0,
        end_s=90.0,
        hook="hook",
        score_viral=5,
        score_relevancia=5,
        clip_path_vertical="/nonexistent/path.mp4",
    )
    video = Video(
        video_id="badclip0001",
        canal_id="c",
        title="T",
        published_at="2026-01-01T00:00:00Z",
    )
    insert_video(db, video)
    insert_clip(db, clip_bad)

    result = upload_clip(
        clip=clip_bad,
        conn=db,
        client_secrets_path=tmp_path / "s.json",
        token_path=tmp_path / "t.json",
    )
    assert result is None


def _make_mock_youtube(youtube_id: str = "YT_VIDEO_ID_123") -> MagicMock:
    mock_request = MagicMock()
    mock_request.next_chunk.return_value = (None, {"id": youtube_id})
    mock_youtube = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_request
    return mock_youtube


def test_upload_clip_success(clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path) -> None:
    mock_youtube = _make_mock_youtube("YT_VIDEO_ID_123")

    with patch(
        "canal_soberania.stages.upload_youtube._get_youtube_service",
        return_value=mock_youtube,
    ), patch("googleapiclient.http.MediaFileUpload", MagicMock()):
        result = upload_clip(
            clip=clip_in_db,
            conn=db,
            client_secrets_path=tmp_path / "s.json",
            token_path=tmp_path / "t.json",
        )

    assert result == "YT_VIDEO_ID_123"
    row = db.execute(
        "SELECT status, youtube_id FROM clips WHERE clip_id=?", (clip_in_db.clip_id,)
    ).fetchone()
    assert row["status"] == "scheduled_youtube"
    assert row["youtube_id"] == "YT_VIDEO_ID_123"


def test_upload_clip_api_error_logs_to_uploads_log(
    clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path
) -> None:
    mock_request = MagicMock()
    mock_request.next_chunk.side_effect = Exception("quota exceeded")
    mock_youtube = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_request

    with patch(
        "canal_soberania.stages.upload_youtube._get_youtube_service",
        return_value=mock_youtube,
    ), patch("googleapiclient.http.MediaFileUpload", MagicMock()):
        result = upload_clip(
            clip=clip_in_db,
            conn=db,
            client_secrets_path=tmp_path / "s.json",
            token_path=tmp_path / "t.json",
        )

    assert result is None
    log = db.execute(
        "SELECT * FROM uploads_log WHERE clip_id=? AND platform='youtube'",
        (clip_in_db.clip_id,),
    ).fetchone()
    assert log["status"] == "error"
    assert "quota exceeded" in log["error_message"]
