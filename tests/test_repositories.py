"""Testes para SqliteVideoRepository, SqliteClipRepository e InMemory fakes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from canal_soberania.core.repositories import ClipRepository, VideoRepository
from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, Video
from canal_soberania.repositories.sqlite import SqliteClipRepository, SqliteVideoRepository
from tests.fakes import InMemoryClipRepository, InMemoryVideoRepository

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


def _video(**kwargs: object) -> Video:
    defaults: dict[str, object] = {
        "video_id": "dQw4w9WgXcQ",
        "canal_id": "flow_podcast",
        "title": "Teste",
        "published_at": "2024-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    return Video.model_validate(defaults)


def _clip(**kwargs: object) -> Clip:
    defaults: dict[str, object] = {
        "clip_id": "dQw4w9WgXcQ_10_40",
        "video_id": "dQw4w9WgXcQ",
        "start_s": 10.0,
        "end_s": 40.0,
    }
    defaults.update(kwargs)
    return Clip.model_validate(defaults)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


def test_sqlite_video_repo_satisfies_protocol(db: sqlite3.Connection) -> None:
    repo = SqliteVideoRepository(db)
    assert isinstance(repo, VideoRepository)


def test_sqlite_clip_repo_satisfies_protocol(db: sqlite3.Connection) -> None:
    repo = SqliteClipRepository(db)
    assert isinstance(repo, ClipRepository)


def test_inmemory_video_repo_satisfies_protocol() -> None:
    repo = InMemoryVideoRepository()
    assert isinstance(repo, VideoRepository)


def test_inmemory_clip_repo_satisfies_protocol() -> None:
    repo = InMemoryClipRepository()
    assert isinstance(repo, ClipRepository)


# ---------------------------------------------------------------------------
# SqliteVideoRepository
# ---------------------------------------------------------------------------


def test_sqlite_video_get_not_found(db: sqlite3.Connection) -> None:
    repo = SqliteVideoRepository(db)
    assert repo.get("xxxxxxxxxxx") is None


def test_sqlite_video_get_found(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    repo = SqliteVideoRepository(db)
    result = repo.get("dQw4w9WgXcQ")
    assert result is not None
    assert result.video_id == "dQw4w9WgXcQ"


def test_sqlite_video_get_all(db: sqlite3.Connection) -> None:
    insert_video(db, _video(video_id="aaaaaaaaa11"))
    insert_video(db, _video(video_id="bbbbbbbbb22"))
    repo = SqliteVideoRepository(db)
    assert len(repo.get_all()) == 2


def test_sqlite_video_get_by_status(db: sqlite3.Connection) -> None:
    insert_video(db, _video(video_id="aaaaaaaaa11"))
    insert_video(db, _video(video_id="bbbbbbbbb22", status="triage_metadata_passed"))
    repo = SqliteVideoRepository(db)
    assert len(repo.get_by_status("discovered")) == 1


def test_sqlite_video_status_summary(db: sqlite3.Connection) -> None:
    insert_video(db, _video(video_id="aaaaaaaaa11"))
    repo = SqliteVideoRepository(db)
    summary = repo.status_summary()
    assert summary.get("discovered", 0) == 1


def test_sqlite_video_monthly_cost_zero(db: sqlite3.Connection) -> None:
    repo = SqliteVideoRepository(db)
    assert repo.monthly_cost() == 0.0


# ---------------------------------------------------------------------------
# SqliteClipRepository
# ---------------------------------------------------------------------------


def test_sqlite_clip_get_not_found(db: sqlite3.Connection) -> None:
    repo = SqliteClipRepository(db)
    assert repo.get("nonexistent_clip") is None


def test_sqlite_clip_get_found(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip())
    repo = SqliteClipRepository(db)
    result = repo.get("dQw4w9WgXcQ_10_40")
    assert result is not None
    assert result.clip_id == "dQw4w9WgXcQ_10_40"


def test_sqlite_clip_get_all(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip())
    repo = SqliteClipRepository(db)
    assert len(repo.get_all()) == 1


def test_sqlite_clip_get_by_status(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip(clip_id="dQw4w9WgXcQ_10_40"))
    insert_clip(db, _clip(clip_id="dQw4w9WgXcQ_50_80", start_s=50.0, end_s=80.0, status="edited"))
    repo = SqliteClipRepository(db)
    assert len(repo.get_by_status("identified")) == 1
    assert len(repo.get_by_status("edited")) == 1


# ---------------------------------------------------------------------------
# InMemoryVideoRepository
# ---------------------------------------------------------------------------


def test_inmemory_video_get_not_found() -> None:
    repo = InMemoryVideoRepository()
    assert repo.get("xxxxxxxxxxx") is None


def test_inmemory_video_get_found() -> None:
    v = _video()
    repo = InMemoryVideoRepository([v])
    assert repo.get("dQw4w9WgXcQ") is not None


def test_inmemory_video_get_all() -> None:
    repo = InMemoryVideoRepository([_video(video_id="aaaaaaaaa11"), _video(video_id="bbbbbbbbb22")])
    assert len(repo.get_all()) == 2


def test_inmemory_video_get_by_status() -> None:
    repo = InMemoryVideoRepository([
        _video(video_id="aaaaaaaaa11", status="discovered"),
        _video(video_id="bbbbbbbbb22", status="triage_metadata_passed"),
    ])
    assert len(repo.get_by_status("discovered")) == 1


def test_inmemory_video_status_summary() -> None:
    repo = InMemoryVideoRepository([
        _video(video_id="aaaaaaaaa11", status="discovered"),
        _video(video_id="bbbbbbbbb22", status="discovered"),
    ])
    assert repo.status_summary()["discovered"] == 2


def test_inmemory_video_add() -> None:
    repo = InMemoryVideoRepository()
    repo.add(_video())
    assert repo.get("dQw4w9WgXcQ") is not None


# ---------------------------------------------------------------------------
# InMemoryClipRepository
# ---------------------------------------------------------------------------


def test_inmemory_clip_get_not_found() -> None:
    repo = InMemoryClipRepository()
    assert repo.get("missing_clip") is None


def test_inmemory_clip_get_found() -> None:
    c = _clip()
    repo = InMemoryClipRepository([c])
    assert repo.get("dQw4w9WgXcQ_10_40") is not None


def test_inmemory_clip_get_all() -> None:
    repo = InMemoryClipRepository([_clip()])
    assert len(repo.get_all()) == 1


def test_inmemory_clip_get_by_status() -> None:
    repo = InMemoryClipRepository([
        _clip(clip_id="dQw4w9WgXcQ_10_40", status="identified"),
        _clip(clip_id="dQw4w9WgXcQ_50_80", start_s=50.0, end_s=80.0, status="edited"),
    ])
    assert len(repo.get_by_status("identified")) == 1


def test_inmemory_clip_add() -> None:
    repo = InMemoryClipRepository()
    repo.add(_clip())
    assert repo.get("dQw4w9WgXcQ_10_40") is not None
