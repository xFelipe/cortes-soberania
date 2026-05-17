"""Conexão SQLite, init_db e helpers de CRUD."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from canal_soberania.models import Clip, ClipStatus, TriageResult, Video, VideoStatus


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path, schema_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    with conn:
        conn.executescript(schema_path.read_text())
    conn.close()


# ---------------------------------------------------------------------------
# Videos
# ---------------------------------------------------------------------------


def insert_video(conn: sqlite3.Connection, video: Video) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO videos (
            video_id, canal_id, title, description, tags,
            published_at, duration_s, view_count, like_count, comment_count,
            audio_path, video_path, caption_path, transcript_path, status
        ) VALUES (
            :video_id, :canal_id, :title, :description, :tags,
            :published_at, :duration_s, :view_count, :like_count, :comment_count,
            :audio_path, :video_path, :caption_path, :transcript_path, :status
        )
        """,
        {
            **video.model_dump(exclude={"created_at", "updated_at"}),
            "tags": json.dumps(video.tags, ensure_ascii=False),
        },
    )


def update_video_status(
    conn: sqlite3.Connection,
    video_id: str,
    status: VideoStatus,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE videos SET status = ?, error_message = ? WHERE video_id = ?",
        (status, error, video_id),
    )


def update_video_paths(
    conn: sqlite3.Connection,
    video_id: str,
    **paths: str | None,
) -> None:
    """Atualiza colunas de caminho: audio_path, video_path, caption_path, transcript_path."""
    valid = {"audio_path", "video_path", "caption_path", "transcript_path"}
    cols = {k: v for k, v in paths.items() if k in valid}
    if not cols:
        return
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(
        f"UPDATE videos SET {sets} WHERE video_id = ?",
        (*cols.values(), video_id),
    )


def get_videos_by_status(conn: sqlite3.Connection, status: VideoStatus) -> list[Video]:
    rows = conn.execute(
        "SELECT * FROM videos WHERE status = ? ORDER BY published_at DESC", (status,)
    ).fetchall()
    return [_row_to_video(row) for row in rows]


def get_videos_by_statuses(
    conn: sqlite3.Connection, statuses: list[VideoStatus]
) -> list[Video]:
    placeholders = ",".join("?" * len(statuses))
    rows = conn.execute(
        f"SELECT * FROM videos WHERE status IN ({placeholders}) ORDER BY published_at DESC",
        statuses,
    ).fetchall()
    return [_row_to_video(row) for row in rows]


def _row_to_video(row: sqlite3.Row) -> Video:
    d: dict[str, Any] = dict(row)
    d["tags"] = json.loads(d["tags"] or "[]")
    return Video.model_validate(d)


# ---------------------------------------------------------------------------
# Triage results
# ---------------------------------------------------------------------------


def insert_triage_result(conn: sqlite3.Connection, result: TriageResult) -> None:
    conn.execute(
        """
        INSERT INTO triage_results (
            video_id, stage, score, is_relevant, themes_detected,
            rationale, raw_response, model_used, tokens_in, tokens_out, cost_usd
        ) VALUES (
            :video_id, :stage, :score, :is_relevant, :themes_detected,
            :rationale, :raw_response, :model_used, :tokens_in, :tokens_out, :cost_usd
        )
        """,
        {
            **result.model_dump(),
            "themes_detected": json.dumps(result.themes_detected, ensure_ascii=False),
            "is_relevant": int(result.is_relevant),
        },
    )


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------


def insert_clip(conn: sqlite3.Connection, clip: Clip) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO clips (
            clip_id, video_id, start_s, end_s, hook, payoff,
            tema_soberania, score_viral, score_relevancia, justificativa,
            clip_path_vertical, clip_path_horizontal, thumb_path,
            title, description, tags, youtube_id, tiktok_id, youtube_publish_at, status
        ) VALUES (
            :clip_id, :video_id, :start_s, :end_s, :hook, :payoff,
            :tema_soberania, :score_viral, :score_relevancia, :justificativa,
            :clip_path_vertical, :clip_path_horizontal, :thumb_path,
            :title, :description, :tags, :youtube_id, :tiktok_id, :youtube_publish_at, :status
        )
        """,
        {
            **clip.model_dump(exclude={"created_at", "updated_at"}),
            "tags": json.dumps(clip.tags, ensure_ascii=False),
        },
    )


def update_clip_status(
    conn: sqlite3.Connection,
    clip_id: str,
    status: ClipStatus,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE clips SET status = ?, error_message = ? WHERE clip_id = ?",
        (status, error, clip_id),
    )


def get_clips_by_status(conn: sqlite3.Connection, status: ClipStatus) -> list[Clip]:
    rows = conn.execute(
        "SELECT * FROM clips WHERE status = ? ORDER BY created_at ASC", (status,)
    ).fetchall()
    return [_row_to_clip(row) for row in rows]


def _row_to_clip(row: sqlite3.Row) -> Clip:
    d: dict[str, Any] = dict(row)
    d["tags"] = json.loads(d["tags"] or "[]")
    d.pop("duracao_s", None)  # coluna virtual calculada, não é campo do model
    return Clip.model_validate(d)


# ---------------------------------------------------------------------------
# API costs
# ---------------------------------------------------------------------------


def record_api_cost(
    conn: sqlite3.Connection,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> None:
    today = date.today().isoformat()
    conn.execute(
        """
        INSERT INTO api_costs (date, provider, model, tokens_in, tokens_out, requests, cost_usd)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT (date, provider, model) DO UPDATE SET
            tokens_in  = tokens_in  + excluded.tokens_in,
            tokens_out = tokens_out + excluded.tokens_out,
            requests   = requests   + 1,
            cost_usd   = cost_usd   + excluded.cost_usd
        """,
        (today, provider, model, tokens_in, tokens_out, cost_usd),
    )


# ---------------------------------------------------------------------------
# Training examples (fine-tuning local)
# ---------------------------------------------------------------------------


def log_training_example(
    conn: sqlite3.Connection,
    task: str,
    prompt: str,
    completion: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    system_prompt: str | None = None,
) -> None:
    """Registra um par prompt/completion para uso futuro em fine-tuning."""
    conn.execute(
        """
        INSERT INTO training_examples
            (task, model, system_prompt, prompt, completion, tokens_in, tokens_out, cost_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (task, model, system_prompt, prompt, completion, tokens_in, tokens_out, cost_usd),
    )


def get_training_examples(
    conn: sqlite3.Connection,
    task: str | None = None,
    approved_only: bool = False,
) -> list[dict[str, object]]:
    """Retorna exemplos de treino, opcionalmente filtrados por task e aprovação."""
    where_clauses: list[str] = []
    params: list[object] = []

    if task:
        where_clauses.append("task = ?")
        params.append(task)
    if approved_only:
        where_clauses.append("approved = 1")

    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = conn.execute(
        f"SELECT * FROM training_examples {where} ORDER BY created_at ASC",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def training_stats(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """Retorna contagem de exemplos por task e status de aprovação."""
    rows = conn.execute(
        """
        SELECT task,
               COUNT(*) AS total,
               SUM(CASE WHEN approved = 1 THEN 1 ELSE 0 END) AS approved,
               SUM(CASE WHEN approved = 0 THEN 1 ELSE 0 END) AS rejected,
               SUM(CASE WHEN approved IS NULL THEN 1 ELSE 0 END) AS uncurated
        FROM training_examples
        GROUP BY task
        ORDER BY task
        """
    ).fetchall()
    return {
        row["task"]: {
            "total": row["total"],
            "approved": row["approved"],
            "rejected": row["rejected"],
            "uncurated": row["uncurated"],
        }
        for row in rows
    }


# ---------------------------------------------------------------------------
# Status summary (para cs status)
# ---------------------------------------------------------------------------


def status_summary(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, total FROM v_status_summary").fetchall()
    return {row["status"]: row["total"] for row in rows}


def monthly_cost(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM v_custo_mes_atual"
    ).fetchone()
    return float(row["total"]) if row else 0.0


def export_training_jsonl(
    conn: sqlite3.Connection,
    output_path: Path,
    task: str | None = None,
    approved_only: bool = True,
) -> int:
    """
    Exporta exemplos de treino para JSONL no formato ChatML (compatível com
    a maioria das ferramentas de fine-tuning: Unsloth, Axolotl, LLaMA-Factory).
    Retorna o número de exemplos exportados.
    """
    examples = get_training_examples(conn, task=task, approved_only=approved_only)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for ex in examples:
            messages: list[dict[str, str]] = []
            if ex.get("system_prompt"):
                messages.append({"role": "system", "content": str(ex["system_prompt"])})
            messages.append({"role": "user", "content": str(ex["prompt"])})
            messages.append({"role": "assistant", "content": str(ex["completion"])})

            record = {
                "messages": messages,
                "_task": ex["task"],
                "_model": ex["model"],
                "_id": ex["id"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return len(examples)
