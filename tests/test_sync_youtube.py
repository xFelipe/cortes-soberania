"""Testes para stages/sync_youtube.py (API YouTube mockada)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, ClipStatus, Video
from canal_soberania.stages.sync_youtube import _int_or_none, run

SCHEMA = Path(__file__).parent.parent / "schema.sql"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    conn = connect(db_path)
    yield conn
    conn.close()


def _make_clip(db: sqlite3.Connection, clip_id: str, status: ClipStatus, yt_id: str | None = None,
               yt_id_h: str | None = None, publish_at: str | None = None) -> Clip:
    video = Video(
        video_id=clip_id[:11],
        canal_id="test_canal",
        title="Vídeo de teste",
        published_at="2026-01-01T00:00:00Z",
    )
    insert_video(db, video)
    clip = Clip(
        clip_id=clip_id,
        video_id=clip_id[:11],
        start_s=0.0,
        end_s=60.0,
        status=status,
        youtube_id=yt_id,
        youtube_publish_at=publish_at,
    )
    insert_clip(db, clip)
    # insert_clip não inclui youtube_id_horizontal (é setado via UPDATE após upload)
    if yt_id_h:
        db.execute(
            "UPDATE clips SET youtube_id_horizontal = ? WHERE clip_id = ?",
            (yt_id_h, clip_id),
        )
        db.commit()
    return clip


def _yt_item(yt_id: str, privacy: str = "private", upload_status: str = "processed",
             publish_at: str | None = "2026-05-20T09:00:00Z",
             rejection_reason: str | None = None,
             published_at: str = "2026-05-20T09:00:01Z",
             views: str = "0", likes: str = "0", comments: str = "0") -> dict:
    status: dict = {"privacyStatus": privacy, "uploadStatus": upload_status}
    if publish_at:
        status["publishAt"] = publish_at
    if rejection_reason:
        status["rejectionReason"] = rejection_reason
    return {
        "id": yt_id,
        "status": status,
        "snippet": {"publishedAt": published_at},
        "statistics": {"viewCount": views, "likeCount": likes, "commentCount": comments},
    }


def _mock_yt(items: list[dict]) -> MagicMock:
    svc = MagicMock()
    svc.videos().list().execute.return_value = {"items": items}
    # Garantir que chamadas subsequentes retornem o mesmo mock
    svc.videos().list.return_value.execute.return_value = {"items": items}
    return svc


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


def test_published_transitions_status(db: sqlite3.Connection) -> None:
    """privacyStatus=public + publishAt ausente → uploaded_youtube + actual_published_at."""
    _make_clip(db, "abc123XYZ01_0_60", ClipStatus.SCHEDULED_YOUTUBE, yt_id="YT_ID_1",
               publish_at="2026-05-20T09:00:00Z")

    item = _yt_item("YT_ID_1", privacy="public", upload_status="processed",
                    publish_at=None, published_at="2026-05-20T09:00:05Z")

    with patch("canal_soberania.stages.sync_youtube.get_youtube_service") as mock_auth:
        mock_auth.return_value = _mock_yt([item])
        run(db, dry_run=False,
            settings=_fake_settings(), paths={})

    row = db.execute("SELECT status, youtube_actual_published_at FROM clips").fetchone()
    assert row["status"] == ClipStatus.UPLOADED_YOUTUBE
    assert row["youtube_actual_published_at"] == "2026-05-20T09:00:05Z"


def test_rejected_transitions_status(db: sqlite3.Connection) -> None:
    """uploadStatus=rejected → rejected_youtube + rejection_reason salvo."""
    _make_clip(db, "abc123XYZ02_0_60", ClipStatus.SCHEDULED_YOUTUBE, yt_id="YT_ID_2")

    item = _yt_item("YT_ID_2", privacy="private", upload_status="rejected",
                    rejection_reason="copyright", publish_at=None)

    with patch("canal_soberania.stages.sync_youtube.get_youtube_service") as mock_auth:
        mock_auth.return_value = _mock_yt([item])
        run(db, dry_run=False, settings=_fake_settings(), paths={})

    row = db.execute("SELECT status, youtube_rejection_reason FROM clips").fetchone()
    assert row["status"] == ClipStatus.REJECTED_YOUTUBE
    assert row["youtube_rejection_reason"] == "copyright"


def test_deleted_video_marks_status(db: sqlite3.Connection) -> None:
    """ID não retorna na lista → deleted_youtube."""
    _make_clip(db, "abc123XYZ03_0_60", ClipStatus.SCHEDULED_YOUTUBE, yt_id="YT_DELETED")

    with patch("canal_soberania.stages.sync_youtube.get_youtube_service") as mock_auth:
        mock_auth.return_value = _mock_yt([])  # YouTube não conhece o ID
        run(db, dry_run=False, settings=_fake_settings(), paths={})

    row = db.execute("SELECT status, youtube_upload_status FROM clips").fetchone()
    assert row["status"] == ClipStatus.DELETED_YOUTUBE
    assert row["youtube_upload_status"] == "deleted"


def test_unscheduled_when_publish_at_removed(db: sqlite3.Connection) -> None:
    """private + publishAt ausente + era scheduled → unscheduled_youtube."""
    _make_clip(db, "abc123XYZ04_0_60", ClipStatus.SCHEDULED_YOUTUBE, yt_id="YT_ID_4",
               publish_at="2026-05-20T09:00:00Z")

    item = _yt_item("YT_ID_4", privacy="private", upload_status="processed",
                    publish_at=None)

    with patch("canal_soberania.stages.sync_youtube.get_youtube_service") as mock_auth:
        mock_auth.return_value = _mock_yt([item])
        run(db, dry_run=False, settings=_fake_settings(), paths={})

    row = db.execute("SELECT status FROM clips").fetchone()
    assert row["status"] == ClipStatus.UNSCHEDULED_YOUTUBE


def test_reschedule_updates_publish_at_without_status_change(db: sqlite3.Connection) -> None:
    """publishAt mudou no YouTube → atualiza coluna, mantém scheduled_youtube."""
    original_at = "2026-05-20T09:00:00Z"
    new_at = "2026-05-21T14:00:00Z"
    _make_clip(db, "abc123XYZ05_0_60", ClipStatus.SCHEDULED_YOUTUBE, yt_id="YT_ID_5",
               publish_at=original_at)

    item = _yt_item("YT_ID_5", privacy="private", upload_status="processed",
                    publish_at=new_at)

    with patch("canal_soberania.stages.sync_youtube.get_youtube_service") as mock_auth:
        mock_auth.return_value = _mock_yt([item])
        run(db, dry_run=False, settings=_fake_settings(), paths={})

    row = db.execute("SELECT status, youtube_publish_at FROM clips").fetchone()
    assert row["status"] == ClipStatus.SCHEDULED_YOUTUBE
    assert row["youtube_publish_at"] == new_at


def test_statistics_updated(db: sqlite3.Connection) -> None:
    """view_count, like_count e comment_count são persistidos."""
    _make_clip(db, "abc123XYZ06_0_60", ClipStatus.UPLOADED_YOUTUBE, yt_id="YT_ID_6")

    item = _yt_item("YT_ID_6", privacy="public", upload_status="processed",
                    publish_at=None, views="12345", likes="678", comments="90")

    with patch("canal_soberania.stages.sync_youtube.get_youtube_service") as mock_auth:
        mock_auth.return_value = _mock_yt([item])
        run(db, dry_run=False, settings=_fake_settings(), paths={})

    row = db.execute("SELECT youtube_view_count, youtube_like_count, youtube_comment_count FROM clips").fetchone()
    assert row["youtube_view_count"] == 12345
    assert row["youtube_like_count"] == 678
    assert row["youtube_comment_count"] == 90


def test_horizontal_does_not_change_clip_status(db: sqlite3.Connection) -> None:
    """Vídeo horizontal deletado não altera o status principal do clipe."""
    _make_clip(db, "abc123XYZ07_0_60", ClipStatus.UPLOADED_YOUTUBE,
               yt_id="YT_VERT_7", yt_id_h="YT_HORZ_7")

    # horizontal deletado; vertical ok
    vert_item = _yt_item("YT_VERT_7", privacy="public", upload_status="processed",
                         publish_at=None, views="100")

    with patch("canal_soberania.stages.sync_youtube.get_youtube_service") as mock_auth:
        # YT_HORZ_7 não retorna — deletado
        mock_auth.return_value = _mock_yt([vert_item])
        run(db, dry_run=False, settings=_fake_settings(), paths={})

    row = db.execute("SELECT status, youtube_id_horizontal, youtube_upload_status_horizontal FROM clips").fetchone()
    assert row["status"] == ClipStatus.UPLOADED_YOUTUBE          # não mudou
    assert row["youtube_id_horizontal"] is None         # limpo
    assert row["youtube_upload_status_horizontal"] == "deleted"


def test_batches_in_groups_of_50(db: sqlite3.Connection) -> None:
    """75 clipes geram 2 chamadas à API (batches de 50)."""
    for i in range(75):
        vid_id = f"VIDID{i:05d}X"[:11]
        # video pode duplicar entre clips; insert_video ignora conflito
        try:
            insert_video(db, Video(
                video_id=vid_id, canal_id="c", title="t",
                published_at="2026-01-01T00:00:00Z",
            ))
        except Exception:
            pass
        clip = Clip(
            clip_id=f"{vid_id}_{i}_60",
            video_id=vid_id,
            start_s=float(i),
            end_s=float(i + 60),
            status=ClipStatus.SCHEDULED_YOUTUBE,
            youtube_id=f"YT_{i:03d}",
        )
        insert_clip(db, clip)

    svc = MagicMock()
    svc.videos().list.return_value.execute.return_value = {"items": []}

    with patch("canal_soberania.stages.sync_youtube.get_youtube_service") as mock_auth:
        mock_auth.return_value = svc
        run(db, dry_run=False, settings=_fake_settings(), paths={})

    assert svc.videos().list.return_value.execute.call_count == 2


def test_dry_run_does_not_write(db: sqlite3.Connection) -> None:
    """dry_run=True não persiste nenhuma mudança no banco."""
    _make_clip(db, "abc123XYZ09_0_60", ClipStatus.SCHEDULED_YOUTUBE, yt_id="YT_ID_9")

    item = _yt_item("YT_ID_9", privacy="public", upload_status="processed",
                    publish_at=None)

    with patch("canal_soberania.stages.sync_youtube.get_youtube_service") as mock_auth:
        mock_auth.return_value = _mock_yt([item])
        run(db, dry_run=True, settings=_fake_settings(), paths={})

    row = db.execute("SELECT status FROM clips").fetchone()
    assert row["status"] == ClipStatus.SCHEDULED_YOUTUBE  # inalterado


def test_int_or_none() -> None:
    assert _int_or_none("123") == 123
    assert _int_or_none(None) is None
    assert _int_or_none("") is None
    assert _int_or_none("abc") is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_settings() -> MagicMock:
    s = MagicMock()
    s.youtube_oauth_client_secrets_path = "config/client_secrets.json"
    s.youtube_oauth_token_path = "config/youtube_token.json"
    return s
