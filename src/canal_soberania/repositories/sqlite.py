"""Implementações SQLite dos repositórios definidos em core/repositories.py."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Literal

from pydantic import ValidationError

from canal_soberania.config import Canal, OutputCanal
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
            f"SELECT v.*, {self._SCORE_SUBQUERY} FROM videos v WHERE v.video_id = ?",  # noqa: S608
            (video_id,),
        ).fetchone()
        return self._row_to_video(row) if row else None

    def get_all(self) -> list[Video]:
        rows = self._conn.execute(
            f"SELECT v.*, {self._SCORE_SUBQUERY} FROM videos v ORDER BY v.published_at DESC"  # noqa: S608
        ).fetchall()
        result = []
        for row in rows:
            d: dict[str, Any] = dict(row)
            d["tags"] = json.loads(d["tags"] or "[]")
            try:
                result.append(Video.model_validate(d))
            except ValidationError:
                d["status"] = VideoStatus.PROCESSING_ERROR
                result.append(Video.model_validate(d))
        return result

    def get_by_status(self, status: VideoStatus) -> list[Video]:
        rows = self._conn.execute(
            f"SELECT v.*, {self._SCORE_SUBQUERY} FROM videos v "  # noqa: S608
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
            "UPDATE videos SET status = ?, "
            "error_message = 'Rejeitado manualmente', updated_at = datetime('now') "
            "WHERE video_id = ?",
            (VideoStatus.TRIAGE_METADATA_REJECTED, video_id),
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
            "UPDATE clips SET status = ?, error_message = ?, "
            "updated_at = datetime('now') WHERE clip_id = ?",
            (ClipStatus.PROCESSING_ERROR, reason, clip_id),
        )
        self._conn.commit()

    def restore(self, clip_id: str) -> None:
        """Restaura clipe de processing_error → identified (desfaz rejeição manual)."""
        self._conn.execute(
            "UPDATE clips SET status = ?, error_message = NULL, "
            "updated_at = datetime('now') WHERE clip_id = ? AND status = ?",
            (ClipStatus.IDENTIFIED, clip_id, ClipStatus.PROCESSING_ERROR),
        )
        self._conn.commit()

    def update_metadata_fields(
        self,
        clip_id: str,
        *,
        hook: str | None = None,
        payoff: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        youtube_publish_at: str | None = None,
        render_vertical: bool | None = None,
        render_horizontal: bool | None = None,
        score_viral: int | None = None,
    ) -> None:
        """UPDATE dinâmico — só altera os campos explicitamente passados (None = não mexer)."""
        scalar: dict[str, Any] = {
            "hook": hook, "payoff": payoff, "title": title,
            "description": description, "youtube_publish_at": youtube_publish_at,
        }
        cols: dict[str, Any] = {k: v for k, v in scalar.items() if v is not None}
        if score_viral is not None:
            cols["score_viral"] = score_viral
        if tags is not None:
            cols["tags"] = json.dumps(tags, ensure_ascii=False)
        if render_vertical is not None:
            cols["render_vertical"] = int(render_vertical)
        if render_horizontal is not None:
            cols["render_horizontal"] = int(render_horizontal)
        if not cols:
            return
        assignments = ", ".join(f"{k} = ?" for k in cols)
        cur = self._conn.execute(
            f"UPDATE clips SET {assignments}, updated_at = datetime('now') WHERE clip_id = ?",  # noqa: S608
            (*cols.values(), clip_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Clip não encontrado: {clip_id}")
        self._conn.commit()

    def clear_platform_id(
        self, clip_id: str, *, kind: Literal["vertical", "horizontal"]
    ) -> None:
        """Limpa youtube_id (vertical) ou youtube_id_horizontal após remoção remota."""
        col = "youtube_id" if kind == "vertical" else "youtube_id_horizontal"
        self._conn.execute(
            f"UPDATE clips SET {col} = NULL, updated_at = datetime('now') WHERE clip_id = ?",  # noqa: S608
            (clip_id,),
        )
        self._conn.commit()

    def update_trim(self, clip_id: str, start_s: float, end_s: float) -> None:
        self._conn.execute(
            "UPDATE clips SET start_s = ?, end_s = ?, updated_at = datetime('now') WHERE clip_id = ?",
            (start_s, end_s, clip_id),
        )
        self._conn.commit()

    def delete(self, clip_id: str) -> None:
        self._conn.execute("DELETE FROM clips WHERE clip_id = ?", (clip_id,))
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


class SqliteCanaisRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── leitura ───────────────────────────────────────────────────────────

    def get_all(self) -> list[Canal]:
        rows = self._conn.execute(
            "SELECT * FROM canais ORDER BY nome ASC"
        ).fetchall()
        return [self._row_to_canal(row) for row in rows]

    def get_active(self) -> list[Canal]:
        rows = self._conn.execute(
            "SELECT * FROM canais WHERE ativo = 1 ORDER BY nome ASC"
        ).fetchall()
        return [self._row_to_canal(row) for row in rows]

    def get(self, canal_id: str) -> Canal | None:
        row = self._conn.execute(
            "SELECT * FROM canais WHERE id = ?", (canal_id,)
        ).fetchone()
        return self._row_to_canal(row) if row else None

    # ── escrita ───────────────────────────────────────────────────────────

    def upsert(self, canal: Canal) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO canais
                       (id, nome, handle, channel_url, tema_primario,
                        peso, auto_publish, tolerancia_cortes, nota, ativo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       nome=excluded.nome,
                       handle=excluded.handle,
                       channel_url=excluded.channel_url,
                       tema_primario=excluded.tema_primario,
                       peso=excluded.peso,
                       auto_publish=excluded.auto_publish,
                       tolerancia_cortes=excluded.tolerancia_cortes,
                       nota=excluded.nota,
                       ativo=excluded.ativo""",
                (
                    canal.id, canal.nome, canal.handle, canal.channel_url,
                    canal.tema_primario, canal.peso,
                    1 if canal.auto_publish else 0,
                    canal.tolerancia_cortes, canal.nota,
                    1 if canal.ativo else 0,
                ),
            )

    def set_active(self, canal_id: str, ativo: bool) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE canais SET ativo = ? WHERE id = ?",
                (1 if ativo else 0, canal_id),
            )

    def delete(self, canal_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM canais WHERE id = ?", (canal_id,))

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_canal(row: sqlite3.Row) -> Canal:
        d: dict[str, Any] = dict(row)
        d["auto_publish"] = bool(d["auto_publish"])
        d["ativo"] = bool(d["ativo"])
        return Canal.model_validate(d)


class SqliteOutputCanaisRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── leitura ───────────────────────────────────────────────────────────

    def get_all(self) -> list[OutputCanal]:
        rows = self._conn.execute(
            "SELECT * FROM output_canais ORDER BY nome ASC"
        ).fetchall()
        return [self._hydrate(row) for row in rows]

    def get_active(self) -> list[OutputCanal]:
        rows = self._conn.execute(
            "SELECT * FROM output_canais WHERE ativo = 1 ORDER BY nome ASC"
        ).fetchall()
        return [self._hydrate(row) for row in rows]

    def get(self, canal_id: str) -> OutputCanal | None:
        row = self._conn.execute(
            "SELECT * FROM output_canais WHERE id = ?", (canal_id,)
        ).fetchone()
        return self._hydrate(row) if row else None

    def get_fontes(self, output_canal_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT fonte_canal_id FROM output_canal_fontes WHERE output_canal_id = ?",
            (output_canal_id,),
        ).fetchall()
        return [row["fonte_canal_id"] for row in rows]

    # ── escrita ───────────────────────────────────────────────────────────

    def upsert(self, canal: OutputCanal) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO output_canais
                       (id, nome, tema, criteria_path, branding_dir,
                        youtube_channel_id, youtube_token_path, ativo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       nome=excluded.nome,
                       tema=excluded.tema,
                       criteria_path=excluded.criteria_path,
                       branding_dir=excluded.branding_dir,
                       youtube_channel_id=excluded.youtube_channel_id,
                       youtube_token_path=excluded.youtube_token_path,
                       ativo=excluded.ativo""",
                (
                    canal.id, canal.nome, canal.tema,
                    canal.criteria_path, canal.branding_dir,
                    canal.youtube_channel_id, canal.youtube_token_path,
                    1 if canal.ativo else 0,
                ),
            )

    def upsert_fontes(self, output_canal_id: str, fontes: list[str]) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM output_canal_fontes WHERE output_canal_id = ?",
                (output_canal_id,),
            )
            for fonte in fontes:
                try:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO output_canal_fontes (output_canal_id, fonte_canal_id) VALUES (?, ?)",
                        (output_canal_id, fonte),
                    )
                except Exception:  # noqa: BLE001
                    pass  # fonte_canal_id não existe ainda em canais (FK violation)

    def update(self, canal_id: str, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        self._conn.execute(
            f"UPDATE output_canais SET {assignments}, updated_at = datetime('now') WHERE id = ?",  # noqa: S608
            (*fields.values(), canal_id),
        )
        self._conn.commit()

    def delete(self, canal_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM output_canais WHERE id = ?", (canal_id,))

    # ── helpers ───────────────────────────────────────────────────────────

    def _hydrate(self, row: sqlite3.Row) -> OutputCanal:
        d: dict[str, Any] = dict(row)
        d["ativo"] = bool(d["ativo"])
        d["fontes"] = self.get_fontes(d["id"])
        return OutputCanal.model_validate(d)
