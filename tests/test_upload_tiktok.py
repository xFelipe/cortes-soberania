"""Testes para stages/upload_tiktok.py."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, ClipStatus, Video
from canal_soberania.stages.upload_tiktok import _safe_filename, queue_clip_for_tiktok

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def mp4(tmp_path: Path) -> Path:
    p = tmp_path / "clips" / "abc123XYZ01_30_90_vertical.mp4"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"fake_video")
    return p


@pytest.fixture
def clip(mp4: Path) -> Clip:
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
        title="Brasil perde soberania industrial",
        description="Análise detalhada sobre desindustrialização.",
        tags=["soberania", "brasil", "industria", "politica", "geopolitica"],
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
# _safe_filename
# ---------------------------------------------------------------------------


def test_safe_filename_basic() -> None:
    assert _safe_filename("Brasil perde soberania") == "brasil_perde_soberania"


def test_safe_filename_strips_special_chars() -> None:
    result = _safe_filename("Análise! (soberania?) #top")
    assert "!" not in result
    assert "?" not in result
    assert "#" not in result


def test_safe_filename_max_len() -> None:
    long_text = "a " * 100
    result = _safe_filename(long_text, max_len=20)
    assert len(result) <= 20


def test_safe_filename_empty_fallback() -> None:
    assert _safe_filename("!!!") == "clip"


# ---------------------------------------------------------------------------
# queue_clip_for_tiktok
# ---------------------------------------------------------------------------


def test_queue_clip_dry_run(clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path) -> None:
    pending = tmp_path / "pending_tiktok"
    result = queue_clip_for_tiktok(clip_in_db, db, pending_dir=pending, dry_run=True)
    assert result is None
    assert not pending.exists() or not list(pending.glob("*.mp4"))


def test_queue_clip_creates_mp4_and_txt(
    clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path
) -> None:
    pending = tmp_path / "pending_tiktok"
    result = queue_clip_for_tiktok(clip_in_db, db, pending_dir=pending)

    assert result is not None
    assert result.exists()
    assert result.suffix == ".mp4"

    txt = result.with_suffix(".txt")
    assert txt.exists()
    content = txt.read_text(encoding="utf-8")
    assert "Brasil perde soberania industrial" in content
    assert "#soberania" in content


def test_queue_clip_updates_status(
    clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path
) -> None:
    pending = tmp_path / "pending_tiktok"
    queue_clip_for_tiktok(clip_in_db, db, pending_dir=pending)

    row = db.execute(
        "SELECT status FROM clips WHERE clip_id=?", (clip_in_db.clip_id,)
    ).fetchone()
    assert row["status"] == ClipStatus.PENDING_TIKTOK_MANUAL


def test_queue_clip_logs_to_uploads_log(
    clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path
) -> None:
    pending = tmp_path / "pending_tiktok"
    queue_clip_for_tiktok(clip_in_db, db, pending_dir=pending)

    log = db.execute(
        "SELECT * FROM uploads_log WHERE clip_id=? AND platform='tiktok'",
        (clip_in_db.clip_id,),
    ).fetchone()
    assert log is not None
    assert log["status"] == "manual_pending"


def test_queue_clip_no_vertical_path(db: sqlite3.Connection, tmp_path: Path) -> None:
    video = Video(
        video_id="nopath00001",
        canal_id="c",
        title="T",
        published_at="2026-01-01T00:00:00Z",
    )
    clip_nv = Clip(
        clip_id="nopath00001_30_90",
        video_id="nopath00001",
        start_s=30.0,
        end_s=90.0,
        hook="h",
        score_viral=5,
        score_relevancia=5,
    )
    insert_video(db, video)
    insert_clip(db, clip_nv)

    pending = tmp_path / "pending_tiktok"
    result = queue_clip_for_tiktok(clip_nv, db, pending_dir=pending)
    assert result is None


def test_queue_clip_missing_file(db: sqlite3.Connection, tmp_path: Path) -> None:
    video = Video(
        video_id="missing0001",
        canal_id="c",
        title="T",
        published_at="2026-01-01T00:00:00Z",
    )
    clip_bad = Clip(
        clip_id="missing0001_30_90",
        video_id="missing0001",
        start_s=30.0,
        end_s=90.0,
        hook="h",
        score_viral=5,
        score_relevancia=5,
        clip_path_vertical="/no/such/file.mp4",
    )
    insert_video(db, video)
    insert_clip(db, clip_bad)

    pending = tmp_path / "pending_tiktok"
    result = queue_clip_for_tiktok(clip_bad, db, pending_dir=pending)
    assert result is None


def test_queue_clip_idempotent(
    clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path
) -> None:
    pending = tmp_path / "pending_tiktok"
    result1 = queue_clip_for_tiktok(clip_in_db, db, pending_dir=pending)
    result2 = queue_clip_for_tiktok(clip_in_db, db, pending_dir=pending)
    assert result1 == result2
