"""Stage 12: move clipe editado para fila manual de upload no TikTok."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from pathlib import Path

from canal_soberania.config import get_paths, load_settings
from canal_soberania.db import connect, get_clips_by_status, init_db
from canal_soberania.logger import logger
from canal_soberania.models import Clip, ClipStatus

_INPUT_STATUS: ClipStatus = "scheduled_youtube"
_PENDING_DIR_NAME = "pending_tiktok"


def _safe_filename(text: str, max_len: int = 60) -> str:
    """Converte texto em slug seguro para nome de arquivo."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "_", slug).strip("_")
    return slug[:max_len] or "clip"


def queue_clip_for_tiktok(
    clip: Clip,
    conn: sqlite3.Connection,
    pending_dir: Path,
    dry_run: bool = False,
) -> Path | None:
    """
    Copia o MP4 vertical e cria um .txt com título/descrição na pasta de pendentes.
    Retorna o path do MP4 copiado, ou None.
    """
    if not clip.clip_path_vertical:
        logger.warning("upload_tiktok: sem clip_path_vertical para {}", clip.clip_id)
        return None

    src = Path(clip.clip_path_vertical)
    if not src.exists():
        logger.warning("upload_tiktok: arquivo não encontrado: {}", src)
        return None

    title = clip.title or clip.hook or clip.clip_id
    slug = _safe_filename(title)
    dst_mp4 = pending_dir / f"{slug}_{clip.clip_id[:8]}.mp4"
    dst_txt = dst_mp4.with_suffix(".txt")

    if dry_run:
        logger.info("[dry-run] upload_tiktok clip={} → {}", clip.clip_id, dst_mp4.name)
        return None

    pending_dir.mkdir(parents=True, exist_ok=True)

    if dst_mp4.exists():
        logger.debug("upload_tiktok: já na fila: {}", dst_mp4.name)
    else:
        shutil.copy2(src, dst_mp4)

    tags_raw = clip.tags or "[]"
    try:
        tags: list[str] = json.loads(tags_raw) if isinstance(tags_raw, str) else list(tags_raw)
    except (json.JSONDecodeError, TypeError):
        tags = []

    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:5])
    description = clip.description or clip.payoff or ""
    sidecar = f"{title}\n\n{description}\n\n{hashtags}\n"
    dst_txt.write_text(sidecar, encoding="utf-8")

    with conn:
        conn.execute(
            "UPDATE clips SET status='pending_tiktok_manual' WHERE clip_id=?",
            (clip.clip_id,),
        )
        conn.execute(
            "INSERT INTO uploads_log (clip_id, platform, status) VALUES (?, 'tiktok', 'manual_pending')",
            (clip.clip_id,),
        )

    logger.info("upload_tiktok: clip={} → {}", clip.clip_id, dst_mp4.name)
    return dst_mp4


def run(
    conn: sqlite3.Connection | None = None,
    dry_run: bool = False,
) -> None:
    """Entry point chamado pelo CLI."""
    settings = load_settings()
    paths = get_paths(settings)

    if conn is None:
        if not paths["db_path"].exists():
            init_db(paths["db_path"], paths["schema_path"])
        conn = connect(paths["db_path"])

    pending_dir = paths["clips_dir"] / _PENDING_DIR_NAME

    clips = get_clips_by_status(conn, _INPUT_STATUS)
    logger.info("upload_tiktok: {} clipes para processar", len(clips))

    queued = 0
    for clip in clips:
        result = queue_clip_for_tiktok(
            clip=clip,
            conn=conn,
            pending_dir=pending_dir,
            dry_run=dry_run or settings.dry_run,
        )
        if result is not None:
            queued += 1

    if queued:
        logger.info(
            "upload_tiktok: {} vídeo(s) pronto(s) em {} — suba pelo app TikTok",
            queued,
            pending_dir,
        )
    logger.info("upload_tiktok concluído | enfileirados={}", queued)
