"""Implementações SQLite dos repositórios definidos em core/repositories.py."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from canal_soberania import db as _db
from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus


class SqliteVideoRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, video_id: str) -> Video | None:
        row = self._conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        if row is None:
            return None
        d: dict[str, Any] = dict(row)
        d["tags"] = json.loads(d["tags"] or "[]")
        return Video.model_validate(d)

    def get_all(self) -> list[Video]:
        rows = self._conn.execute(
            "SELECT * FROM videos ORDER BY published_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            d: dict[str, Any] = dict(row)
            d["tags"] = json.loads(d["tags"] or "[]")
            result.append(Video.model_validate(d))
        return result

    def get_by_status(self, status: VideoStatus) -> list[Video]:
        return _db.get_videos_by_status(self._conn, status)

    def status_summary(self) -> dict[str, int]:
        return _db.status_summary(self._conn)

    def monthly_cost(self) -> float:
        return _db.monthly_cost(self._conn)


class SqliteClipRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, clip_id: str) -> Clip | None:
        row = self._conn.execute(
            "SELECT * FROM clips WHERE clip_id = ?", (clip_id,)
        ).fetchone()
        if row is None:
            return None
        d: dict[str, Any] = dict(row)
        d["tags"] = json.loads(d["tags"] or "[]")
        d.pop("duracao_s", None)
        return Clip.model_validate(d)

    def get_all(self) -> list[Clip]:
        rows = self._conn.execute(
            "SELECT * FROM clips ORDER BY created_at ASC"
        ).fetchall()
        result = []
        for row in rows:
            d: dict[str, Any] = dict(row)
            d["tags"] = json.loads(d["tags"] or "[]")
            d.pop("duracao_s", None)
            result.append(Clip.model_validate(d))
        return result

    def get_by_status(self, status: ClipStatus) -> list[Clip]:
        return _db.get_clips_by_status(self._conn, status)
