"""PipelineService — ponto de entrada único para CLI e futuras UIs (PySide6, FastAPI)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from canal_soberania import db as _db
from canal_soberania.config import Settings
from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus


class PipelineService:
    """Orquestra os stages do pipeline e expõe queries para a camada de apresentação.

    Recebe dependências por injeção no construtor — nenhum import de GUI ou HTTP
    dentro desta classe.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings,
        paths: dict[str, Path],
    ) -> None:
        self._conn = conn
        self._settings = settings
        self._paths = paths

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_status_summary(self) -> dict[str, int]:
        return _db.status_summary(self._conn)

    def get_monthly_cost(self) -> float:
        return _db.monthly_cost(self._conn)

    def get_video(self, video_id: str) -> Video | None:
        row = self._conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        if row is None:
            return None
        d: dict[str, Any] = dict(row)
        import json
        d["tags"] = json.loads(d["tags"] or "[]")
        return Video.model_validate(d)

    def get_videos(self, status: VideoStatus | None = None) -> list[Video]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM videos ORDER BY published_at DESC"
            ).fetchall()
            import json
            result = []
            for row in rows:
                d: dict[str, Any] = dict(row)
                d["tags"] = json.loads(d["tags"] or "[]")
                result.append(Video.model_validate(d))
            return result
        return _db.get_videos_by_status(self._conn, status)

    def get_clips(self, status: ClipStatus | None = None) -> list[Clip]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM clips ORDER BY created_at ASC"
            ).fetchall()
            import json
            result = []
            for row in rows:
                d: dict[str, Any] = dict(row)
                d["tags"] = json.loads(d["tags"] or "[]")
                d.pop("duracao_s", None)
                result.append(Clip.model_validate(d))
            return result
        return _db.get_clips_by_status(self._conn, status)

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    def run_discover(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.discover import run
        run(conn=self._conn, dry_run=dry_run)

    def run_triage_metadata(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.triage_metadata import run
        run(conn=self._conn, dry_run=dry_run)

    def run_triage_caption(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.triage_caption import run
        run(conn=self._conn, dry_run=dry_run)

    def run_triage_transcript(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.triage_transcript import run
        run(conn=self._conn, dry_run=dry_run)

    def run_download(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.download import run
        run(conn=self._conn, dry_run=dry_run)

    def run_transcribe(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.transcribe import run
        run(conn=self._conn, dry_run=dry_run)

    def run_find_clips(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.find_clips import run
        run(conn=self._conn, dry_run=dry_run)

    def run_edit(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.edit import run
        run(conn=self._conn, dry_run=dry_run)

    def run_thumbnail(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.thumbnail import run
        run(conn=self._conn, dry_run=dry_run)

    def run_generate_metadata(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.metadata import run
        run(conn=self._conn, dry_run=dry_run)

    def run_upload_youtube(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.upload_youtube import run
        run(conn=self._conn, dry_run=dry_run)

    def run_upload_tiktok(self, dry_run: bool = False) -> None:
        from canal_soberania.stages.upload_tiktok import run
        run(conn=self._conn, dry_run=dry_run)
