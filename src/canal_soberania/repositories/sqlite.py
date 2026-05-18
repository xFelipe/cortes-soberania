"""Implementações SQLite dos repositórios definidos em core/repositories.py."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from pydantic import ValidationError

from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus


class SqliteVideoRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── leitura ───────────────────────────────────────────────────────────

    _SCORE_SUBQUERY = (
        "(SELECT score FROM triage_results tr "
        " WHERE tr.video_id = v.video_id "
        " ORDER BY CASE tr.stage "
        "   WHEN 'transcript' THEN 3 "
        "   WHEN 'caption' THEN 2 "
        "   ELSE 1 END DESC, tr.created_at DESC "
        " LIMIT 1) AS score_triage"
    )

    def get(self, video_id: str) -> Video | None:
        row = self._conn.execute(
            f"SELECT v.*, {self._SCORE_SUBQUERY} FROM videos v WHERE v.video_id = ?",
            (video_id,),
        ).fetchone()
        return self._row_to_video(row) if row else None

    def get_all(self) -> list[Video]:
        rows = self._conn.execute(
            f"SELECT v.*, {self._SCORE_SUBQUERY} FROM videos v ORDER BY v.published_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            d: dict[str, Any] = dict(row)
            d["tags"] = json.loads(d["tags"] or "[]")
            try:
                result.append(Video.model_validate(d))
            except ValidationError:
                d["status"] = "processing_error"
                result.append(Video.model_validate(d))
        return result

    def get_by_status(self, status: VideoStatus) -> list[Video]:
        rows = self._conn.execute(
            f"SELECT v.*, {self._SCORE_SUBQUERY} FROM videos v "
            "WHERE v.status = ? ORDER BY v.published_at DESC",
            (status,),
        ).fetchall()
        return [self._row_to_video(row) for row in rows]

    def status_summary(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, total FROM v_status_summary"
        ).fetchall()
        return {row["status"]: row["total"] for row in rows}

    def monthly_cost(self) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM v_custo_mes_atual"
        ).fetchone()
        return float(row["total"]) if row else 0.0

    # ── escrita ───────────────────────────────────────────────────────────

    def update_status(self, video_id: str, new_status: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE videos SET status = ?, updated_at = datetime('now') WHERE video_id = ?",
                (new_status, video_id),
            )

    def reject(self, video_id: str) -> None:
        self._conn.execute(
            "UPDATE videos SET status = 'triage_metadata_rejected', "
            "error_message = 'Rejeitado manualmente', updated_at = datetime('now') "
            "WHERE video_id = ?",
            (video_id,),
        )
        self._conn.commit()

    def reset_stuck(self, stuck_configs: list[tuple[str, str]]) -> int:
        """Reseta vídeos cujo heartbeat está atrasado ≥ 3 min (processo morreu mid-execução)."""
        from canal_soberania.logger import logger

        total = 0
        for stuck_status, reset_to in stuck_configs:
            cur = self._conn.execute(
                "UPDATE videos "
                "SET status = ?, processing_since = NULL, updated_at = datetime('now') "
                "WHERE status = ? "
                "  AND processing_since IS NOT NULL "
                "  AND processing_since < datetime('now', '-3 minutes')",
                (reset_to, stuck_status),
            )
            if cur.rowcount > 0:
                self._conn.commit()
                logger.info(
                    "reset_stuck: {} vídeo(s) '{}' → '{}' (heartbeat expirado)",
                    cur.rowcount, stuck_status, reset_to,
                )
                total += cur.rowcount
        return total

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_video(row: sqlite3.Row) -> Video:
        d: dict[str, Any] = dict(row)
        d["tags"] = json.loads(d["tags"] or "[]")
        return Video.model_validate(d)


class SqliteClipRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── leitura ───────────────────────────────────────────────────────────

    def get(self, clip_id: str) -> Clip | None:
        row = self._conn.execute(
            "SELECT * FROM clips WHERE clip_id = ?", (clip_id,)
        ).fetchone()
        return self._row_to_clip(row) if row else None

    def get_all(self) -> list[Clip]:
        rows = self._conn.execute(
            "SELECT * FROM clips ORDER BY created_at ASC"
        ).fetchall()
        return [self._row_to_clip(row) for row in rows]

    def get_by_status(self, status: ClipStatus) -> list[Clip]:
        rows = self._conn.execute(
            "SELECT * FROM clips WHERE status = ? ORDER BY created_at ASC", (status,)
        ).fetchall()
        return [self._row_to_clip(row) for row in rows]

    # ── escrita ───────────────────────────────────────────────────────────

    def update_text(
        self,
        clip_id: str,
        hook: str | None,
        payoff: str | None,
        title: str | None,
        youtube_publish_at: str | None,
        render_vertical: bool = True,
        render_horizontal: bool = True,
    ) -> None:
        cur = self._conn.execute(
            "UPDATE clips SET hook = ?, payoff = ?, title = ?, youtube_publish_at = ?, "
            "render_vertical = ?, render_horizontal = ?, "
            "updated_at = datetime('now') WHERE clip_id = ?",
            (hook, payoff, title, youtube_publish_at,
             1 if render_vertical else 0, 1 if render_horizontal else 0,
             clip_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Clip não encontrado no banco: {clip_id}")
        self._conn.commit()

    def update_status(self, clip_id: str, new_status: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE clips SET status = ?, updated_at = datetime('now') WHERE clip_id = ?",
                (new_status, clip_id),
            )

    def reject(self, clip_id: str, reason: str) -> None:
        self._conn.execute(
            "UPDATE clips SET status = 'processing_error', error_message = ?, "
            "updated_at = datetime('now') WHERE clip_id = ?",
            (reason, clip_id),
        )
        self._conn.commit()

    def restore(self, clip_id: str) -> None:
        """Restaura clipe de processing_error → identified (desfaz rejeição manual)."""
        self._conn.execute(
            "UPDATE clips SET status = 'identified', error_message = NULL, "
            "updated_at = datetime('now') WHERE clip_id = ? AND status = 'processing_error'",
            (clip_id,),
        )
        self._conn.commit()

    def update_trim(self, clip_id: str, start_s: float, end_s: float) -> None:
        self._conn.execute(
            "UPDATE clips SET start_s = ?, end_s = ?, updated_at = datetime('now') WHERE clip_id = ?",
            (start_s, end_s, clip_id),
        )
        self._conn.commit()

    def reset_stuck(self, stuck_configs: list[tuple[str, str]]) -> int:
        """Reseta clipes cujo heartbeat está atrasado ≥ 3 min (processo morreu mid-execução)."""
        from canal_soberania.logger import logger

        total = 0
        for stuck_status, reset_to in stuck_configs:
            cur = self._conn.execute(
                "UPDATE clips "
                "SET status = ?, processing_since = NULL, updated_at = datetime('now') "
                "WHERE status = ? "
                "  AND processing_since IS NOT NULL "
                "  AND processing_since < datetime('now', '-3 minutes')",
                (reset_to, stuck_status),
            )
            if cur.rowcount > 0:
                self._conn.commit()
                logger.info(
                    "reset_stuck: {} clipe(s) '{}' → '{}' (heartbeat expirado)",
                    cur.rowcount, stuck_status, reset_to,
                )
                total += cur.rowcount
        return total

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_clip(row: sqlite3.Row) -> Clip:
        d: dict[str, Any] = dict(row)
        d["tags"] = json.loads(d["tags"] or "[]")
        d.pop("duracao_s", None)
        return Clip.model_validate(d)
