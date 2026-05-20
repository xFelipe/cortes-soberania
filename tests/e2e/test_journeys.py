"""E2E journeys — API-level, sem browser.

Sobe o app FastAPI com PipelineService real + SQLite :memory: e executa os 3
cenários de uso ponta-a-ponta via TestClient.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from canal_soberania.api.app import create_app
from canal_soberania.config import CanaisConfig, Parametros, Settings
from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus
from canal_soberania.services.pipeline_service import PipelineService

_SCHEMA = Path(__file__).parent.parent.parent / "schema.sql"
_MIGRATIONS = Path(__file__).parent.parent.parent / "migrations"
_TOKEN = "e2e-test-token"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for sql_file in sorted(_MIGRATIONS.glob("*.sql")):
        try:
            conn.executescript(sql_file.read_text())
        except Exception:  # noqa: BLE001
            pass


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "e2e.db"
    init_db(db_path, _SCHEMA)
    c = connect(db_path)
    _apply_migrations(c)
    return c


@pytest.fixture()
def service(db: sqlite3.Connection, tmp_path: Path) -> PipelineService:
    settings = Settings(data_dir=tmp_path)
    paths: dict[str, Path] = {
        "data_dir": tmp_path,
        "db_path": tmp_path / "e2e.db",
        "schema_path": _SCHEMA,
        "log_dir": tmp_path / "logs",
    }
    return PipelineService(conn=db, settings=settings, paths=paths)


@pytest.fixture()
def client(service: PipelineService, db: sqlite3.Connection, tmp_path: Path) -> TestClient:
    canais_cfg = CanaisConfig(canais=[], parametros=Parametros())
    app = create_app(
        service=service,
        conn=db,
        paths={"data_dir": tmp_path, "log_dir": tmp_path / "logs"},
        token=_TOKEN,
        canais_cfg=canais_cfg,
    )
    return TestClient(app, raise_server_exceptions=True)


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _make_video(video_id: str = "aaaaaaaaaaa") -> Video:
    return Video(
        video_id=video_id,
        canal_id="flow_podcast",
        title="Soberania Nacional ep. 1",
        published_at="2024-06-01T10:00:00Z",
        status=VideoStatus.CLIPS_FOUND,
    )


def _make_clip(
    clip_id: str = "aaaaaaaaaaa_10_70",
    video_id: str = "aaaaaaaaaaa",
    status: ClipStatus = ClipStatus.METADATA_READY,
) -> Clip:
    return Clip(
        clip_id=clip_id,
        video_id=video_id,
        start_s=10.0,
        end_s=70.0,
        hook="Hook de teste",
        title="Título do clipe",
        status=status,
    )


# ---------------------------------------------------------------------------
# Cenário 1 — Aprovar clipe end-to-end
# ---------------------------------------------------------------------------


def test_journey_approve_clip(
    client: TestClient,
    service: PipelineService,
    db: sqlite3.Connection,
) -> None:
    """METADATA_READY clip aparece no /inbox → POST /approve retorna upload_started."""
    insert_video(db, _make_video())
    insert_clip(db, _make_clip())

    # Clip deve aparecer no inbox
    r = client.get("/inbox", headers=_auth())
    assert r.status_code == 200
    inbox = r.json()
    clip_ids = [item["clip_id"] for item in inbox["items"] if "clip_id" in item]
    assert "aaaaaaaaaaa_10_70" in clip_ids

    # Aprovar o clipe (dispara thread de upload — não esperamos conclusão)
    r = client.post("/clips/aaaaaaaaaaa_10_70/approve", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "upload_started"
    assert body["clip_id"] == "aaaaaaaaaaa_10_70"


# ---------------------------------------------------------------------------
# Cenário 2 — Bulk approve 3 clipes
# ---------------------------------------------------------------------------


def test_journey_bulk_approve_clips(
    client: TestClient,
    service: PipelineService,
    db: sqlite3.Connection,
) -> None:
    """3 clipes METADATA_READY → 3 approves → /stats/summary reflete vídeo."""
    insert_video(db, _make_video())
    for i in range(3):
        insert_clip(
            db,
            _make_clip(clip_id=f"aaaaaaaaaaa_{i*10}_{i*10+60}", status=ClipStatus.METADATA_READY),
        )

    # Verificar que os 3 clipes estão na inbox
    r = client.get("/inbox", headers=_auth())
    assert r.status_code == 200
    clip_items = [item for item in r.json()["items"] if "clip_id" in item]
    assert len(clip_items) == 3

    # Aprovar todos
    approved = 0
    for item in clip_items:
        r = client.post(f"/clips/{item['clip_id']}/approve", headers=_auth())
        assert r.status_code == 200
        approved += 1
    assert approved == 3

    # Stats devem refletir o vídeo inserido
    r = client.get("/stats/summary", headers=_auth())
    assert r.status_code == 200
    summary = r.json()
    total = sum(summary.values()) if isinstance(summary, dict) else 0
    assert total >= 1


# ---------------------------------------------------------------------------
# Cenário 3 — Rejeitar vídeo + restaurar via approve
# ---------------------------------------------------------------------------


def test_journey_reject_and_restore_video(
    client: TestClient,
    service: PipelineService,
    db: sqlite3.Connection,
) -> None:
    """DISCOVERED video → reject → TRIAGE_METADATA_REJECTED → approve → TRIAGE_METADATA_PASSED."""
    insert_video(db, _make_video(video_id="bbbbbbbbbbb").model_copy(
        update={"status": VideoStatus.DISCOVERED}
    ))

    # Rejeitar
    r = client.post("/videos/bbbbbbbbbbb/reject", headers=_auth())
    assert r.status_code == 200

    video = service.get_video("bbbbbbbbbbb")
    assert video is not None
    assert video.status == VideoStatus.TRIAGE_METADATA_REJECTED

    # Restaurar via approve (REJECTED → PASSED)
    r = client.post("/videos/bbbbbbbbbbb/approve", headers=_auth())
    assert r.status_code == 200

    video = service.get_video("bbbbbbbbbbb")
    assert video is not None
    assert video.status == VideoStatus.TRIAGE_METADATA_PASSED


# ---------------------------------------------------------------------------
# Cenário bonus — Rejeitar clipe + verificar status
# ---------------------------------------------------------------------------


def test_journey_reject_clip(
    client: TestClient,
    service: PipelineService,
    db: sqlite3.Connection,
) -> None:
    """Clip em qualquer status → POST /clips/{id}/reject → REJECTED_YOUTUBE."""
    insert_video(db, _make_video())
    insert_clip(db, _make_clip(status=ClipStatus.METADATA_READY))

    r = client.post("/clips/aaaaaaaaaaa_10_70/reject", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"

    clip = service.get_clip("aaaaaaaaaaa_10_70")
    assert clip is not None
    assert clip.status == ClipStatus.REJECTED_YOUTUBE


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
