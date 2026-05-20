"""Testes para SqliteVideoRepository, SqliteClipRepository e InMemory fakes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from canal_soberania.core.repositories import ClipRepository, VideoRepository
from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus
from canal_soberania.config import Canal
from canal_soberania.repositories.sqlite import (
    SqliteCanaisRepository,
    SqliteClipRepository,
    SqliteVideoRepository,
)
from tests.fakes import InMemoryClipRepository, InMemoryVideoRepository

SCHEMA = Path(__file__).parent.parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Aplica todas as migrations em ordem para que o schema de teste esteja completo."""
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        try:
            conn.executescript(sql_file.read_text())
        except Exception:  # noqa: BLE001 — ignorar conflitos de coluna já existente
            pass


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    c = connect(db_path)
    _apply_migrations(c)
    return c


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
    insert_video(db, _video(video_id="bbbbbbbbb22", status=VideoStatus.TRIAGE_METADATA_PASSED))
    repo = SqliteVideoRepository(db)
    assert len(repo.get_by_status(VideoStatus.DISCOVERED)) == 1


def test_sqlite_video_status_summary(db: sqlite3.Connection) -> None:
    insert_video(db, _video(video_id="aaaaaaaaa11"))
    repo = SqliteVideoRepository(db)
    summary = repo.status_summary()
    assert summary.get(VideoStatus.DISCOVERED, 0) == 1


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
    insert_clip(db, _clip(clip_id="dQw4w9WgXcQ_50_80", start_s=50.0, end_s=80.0, status=ClipStatus.EDITED))
    repo = SqliteClipRepository(db)
    assert len(repo.get_by_status(ClipStatus.IDENTIFIED)) == 1
    assert len(repo.get_by_status(ClipStatus.EDITED)) == 1


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
        _video(video_id="aaaaaaaaa11", status=VideoStatus.DISCOVERED),
        _video(video_id="bbbbbbbbb22", status=VideoStatus.TRIAGE_METADATA_PASSED),
    ])
    assert len(repo.get_by_status(VideoStatus.DISCOVERED)) == 1


def test_inmemory_video_status_summary() -> None:
    repo = InMemoryVideoRepository([
        _video(video_id="aaaaaaaaa11", status=VideoStatus.DISCOVERED),
        _video(video_id="bbbbbbbbb22", status=VideoStatus.DISCOVERED),
    ])
    assert repo.status_summary()[VideoStatus.DISCOVERED] == 2


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
        _clip(clip_id="dQw4w9WgXcQ_10_40", status=ClipStatus.IDENTIFIED),
        _clip(clip_id="dQw4w9WgXcQ_50_80", start_s=50.0, end_s=80.0, status=ClipStatus.EDITED),
    ])
    assert len(repo.get_by_status(ClipStatus.IDENTIFIED)) == 1


def test_inmemory_clip_add() -> None:
    repo = InMemoryClipRepository()
    repo.add(_clip())
    assert repo.get("dQw4w9WgXcQ_10_40") is not None


# ---------------------------------------------------------------------------
# SqliteVideoRepository — escrita
# ---------------------------------------------------------------------------


def test_sqlite_video_update_status(db: sqlite3.Connection) -> None:
    insert_video(db, _video(status=VideoStatus.DISCOVERED))
    repo = SqliteVideoRepository(db)
    repo.update_status("dQw4w9WgXcQ", VideoStatus.TRIAGE_METADATA_PASSED)
    updated = repo.get("dQw4w9WgXcQ")
    assert updated is not None
    assert updated.status == VideoStatus.TRIAGE_METADATA_PASSED


def test_sqlite_video_reject(db: sqlite3.Connection) -> None:
    insert_video(db, _video(status=VideoStatus.DISCOVERED))
    repo = SqliteVideoRepository(db)
    repo.reject("dQw4w9WgXcQ")
    updated = repo.get("dQw4w9WgXcQ")
    assert updated is not None
    assert updated.status == VideoStatus.TRIAGE_METADATA_REJECTED


def test_sqlite_video_reset_stuck_no_rows(db: sqlite3.Connection) -> None:
    repo = SqliteVideoRepository(db)
    count = repo.reset_stuck([(VideoStatus.DOWNLOADING, VideoStatus.TRIAGE_CAPTION_PASSED)])
    assert count == 0


# ---------------------------------------------------------------------------
# SqliteClipRepository — escrita
# ---------------------------------------------------------------------------


def test_sqlite_clip_update_text(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip())
    repo = SqliteClipRepository(db)
    repo.update_text("dQw4w9WgXcQ_10_40", "Novo hook", "Payoff", "Título", None)
    updated = repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.hook == "Novo hook"
    assert updated.title == "Título"


def test_sqlite_clip_update_text_not_found(db: sqlite3.Connection) -> None:
    repo = SqliteClipRepository(db)
    with pytest.raises(ValueError, match="não encontrado no banco"):
        repo.update_text("nonexistent_0_60", "h", "p", "t", None)


def test_sqlite_clip_update_status(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip())
    repo = SqliteClipRepository(db)
    repo.update_status("dQw4w9WgXcQ_10_40", ClipStatus.EDITED)
    updated = repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.status == ClipStatus.EDITED


def test_sqlite_clip_reject(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip())
    repo = SqliteClipRepository(db)
    repo.reject("dQw4w9WgXcQ_10_40", "Fora do tema")
    updated = repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.status == ClipStatus.PROCESSING_ERROR
    assert updated.error_message == "Fora do tema"


def test_sqlite_clip_restore(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip(status=ClipStatus.PROCESSING_ERROR))
    repo = SqliteClipRepository(db)
    repo.restore("dQw4w9WgXcQ_10_40")
    updated = repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.status == ClipStatus.IDENTIFIED


def test_sqlite_clip_update_metadata_fields(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip())
    repo = SqliteClipRepository(db)
    repo.update_metadata_fields(
        "dQw4w9WgXcQ_10_40",
        hook="Hook novo",
        title="Título novo",
        score_viral=8,
        tags=["soberania", "brasil"],
        render_vertical=True,
        render_horizontal=False,
    )
    updated = repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.hook == "Hook novo"
    assert updated.score_viral == 8
    assert "soberania" in updated.tags


def test_sqlite_clip_update_metadata_fields_not_found(db: sqlite3.Connection) -> None:
    repo = SqliteClipRepository(db)
    with pytest.raises(ValueError, match="não encontrado"):
        repo.update_metadata_fields("nonexistent_0_60", hook="h")


def test_sqlite_clip_update_metadata_fields_no_changes(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip())
    repo = SqliteClipRepository(db)
    # Deve retornar sem erro quando nada é passado
    repo.update_metadata_fields("dQw4w9WgXcQ_10_40")


def test_sqlite_clip_clear_platform_id_vertical(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip(youtube_id="YT_001"))
    repo = SqliteClipRepository(db)
    repo.clear_platform_id("dQw4w9WgXcQ_10_40", kind="vertical")
    updated = repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.youtube_id is None


def test_sqlite_clip_clear_platform_id_horizontal(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip(youtube_id_horizontal="YT_H01"))
    repo = SqliteClipRepository(db)
    repo.clear_platform_id("dQw4w9WgXcQ_10_40", kind="horizontal")
    updated = repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.youtube_id_horizontal is None


def test_sqlite_clip_update_trim(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip())
    repo = SqliteClipRepository(db)
    repo.update_trim("dQw4w9WgXcQ_10_40", 20.0, 55.0)
    updated = repo.get("dQw4w9WgXcQ_10_40")
    assert updated is not None
    assert updated.start_s == 20.0
    assert updated.end_s == 55.0


def test_sqlite_clip_delete(db: sqlite3.Connection) -> None:
    insert_video(db, _video())
    insert_clip(db, _clip())
    repo = SqliteClipRepository(db)
    repo.delete("dQw4w9WgXcQ_10_40")
    assert repo.get("dQw4w9WgXcQ_10_40") is None


def test_sqlite_clip_reset_stuck_no_rows(db: sqlite3.Connection) -> None:
    repo = SqliteClipRepository(db)
    count = repo.reset_stuck([(ClipStatus.EDITING, ClipStatus.IDENTIFIED)])
    assert count == 0


# ---------------------------------------------------------------------------
# SqliteCanaisRepository
# ---------------------------------------------------------------------------


def _canal(**kwargs: object) -> Canal:
    defaults: dict[str, object] = {
        "id": "flow_podcast",
        "nome": "Flow Podcast",
        "handle": "@flowpodcast",
        "channel_url": "https://youtube.com/@flowpodcast",
        "tema_primario": "soberania",
    }
    defaults.update(kwargs)
    return Canal.model_validate(defaults)


def test_sqlite_canais_empty(db: sqlite3.Connection) -> None:
    repo = SqliteCanaisRepository(db)
    assert repo.get_all() == []
    assert repo.get_active() == []


def test_sqlite_canais_upsert_and_get_all(db: sqlite3.Connection) -> None:
    repo = SqliteCanaisRepository(db)
    repo.upsert(_canal())
    result = repo.get_all()
    assert len(result) == 1
    assert result[0].id == "flow_podcast"
    assert result[0].nome == "Flow Podcast"


def test_sqlite_canais_upsert_updates(db: sqlite3.Connection) -> None:
    repo = SqliteCanaisRepository(db)
    repo.upsert(_canal(nome="Antigo"))
    repo.upsert(_canal(nome="Atualizado"))
    result = repo.get_all()
    assert len(result) == 1
    assert result[0].nome == "Atualizado"


def test_sqlite_canais_get_active(db: sqlite3.Connection) -> None:
    repo = SqliteCanaisRepository(db)
    repo.upsert(_canal(id="ativo", ativo=True))
    repo.upsert(_canal(id="inativo", ativo=False))
    active = repo.get_active()
    assert len(active) == 1
    assert active[0].id == "ativo"


def test_sqlite_canais_get_by_id(db: sqlite3.Connection) -> None:
    repo = SqliteCanaisRepository(db)
    repo.upsert(_canal())
    found = repo.get("flow_podcast")
    assert found is not None
    assert found.nome == "Flow Podcast"
    assert repo.get("nonexistent") is None


def test_sqlite_canais_set_active(db: sqlite3.Connection) -> None:
    repo = SqliteCanaisRepository(db)
    repo.upsert(_canal(ativo=True))
    repo.set_active("flow_podcast", False)
    updated = repo.get("flow_podcast")
    assert updated is not None
    assert updated.ativo is False


def test_sqlite_canais_delete(db: sqlite3.Connection) -> None:
    repo = SqliteCanaisRepository(db)
    repo.upsert(_canal())
    repo.delete("flow_podcast")
    assert repo.get("flow_podcast") is None
