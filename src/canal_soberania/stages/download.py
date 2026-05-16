"""Stage 4: baixa áudio (MP3) e vídeo (MP4 1080p) via yt-dlp."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import yt_dlp  # type: ignore[import-untyped]

from canal_soberania.config import get_paths, load_settings
from canal_soberania.db import (
    connect,
    get_videos_by_status,
    init_db,
    update_video_paths,
    update_video_status,
)
from canal_soberania.logger import logger
from canal_soberania.models import Video

# Statuses que entram no stage de download
_INPUT_STATUSES = ("triage_caption_passed", "triage_caption_skipped")


def _ydl_audio_opts(dest_path: Path) -> dict[str, Any]:
    return {
        "format": "bestaudio/best",
        "outtmpl": str(dest_path.with_suffix(".%(ext)s")),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }


def _ydl_video_opts(dest_path: Path) -> dict[str, Any]:
    return {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "outtmpl": str(dest_path),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }


def download_audio(video_id: str, audio_dir: Path, dry_run: bool = False) -> Path | None:
    """Baixa áudio como MP3. Retorna o path do arquivo ou None em caso de erro."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    dest = audio_dir / f"{video_id}.mp3"

    if dest.exists():
        logger.debug("Áudio já existe: {}", dest)
        return dest

    if dry_run:
        logger.info("[dry-run] download_audio {}", video_id)
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = _ydl_audio_opts(audio_dir / video_id)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.error("yt-dlp audio error {}: {}", video_id, exc)
        return None

    return dest if dest.exists() else None


def download_video(video_id: str, video_dir: Path, dry_run: bool = False) -> Path | None:
    """Baixa vídeo em até 1080p como MP4. Retorna o path ou None em caso de erro."""
    video_dir.mkdir(parents=True, exist_ok=True)
    dest = video_dir / f"{video_id}.mp4"

    if dest.exists():
        logger.debug("Vídeo já existe: {}", dest)
        return dest

    if dry_run:
        logger.info("[dry-run] download_video {}", video_id)
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = _ydl_video_opts(dest)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.error("yt-dlp video error {}: {}", video_id, exc)
        return None

    return dest if dest.exists() else None


def download_video_assets(
    video: Video,
    conn: sqlite3.Connection,
    audio_dir: Path,
    video_dir: Path,
    dry_run: bool = False,
) -> bool:
    """
    Baixa áudio + vídeo para um vídeo. Atualiza paths e status no banco.
    Retorna True se ao menos o áudio foi baixado com sucesso.
    """
    if not dry_run:
        with conn:
            update_video_status(conn, video.video_id, "downloading")

    audio_path = download_audio(video.video_id, audio_dir, dry_run=dry_run)
    video_path = download_video(video.video_id, video_dir, dry_run=dry_run)

    if dry_run:
        return True

    if audio_path is None:
        logger.error("Falha no download de áudio para {}", video.video_id)
        with conn:
            update_video_status(
                conn, video.video_id, "processing_error", "audio_download_failed"
            )
        return False

    with conn:
        update_video_paths(
            conn,
            video.video_id,
            audio_path=str(audio_path),
            video_path=str(video_path) if video_path else None,
        )
        update_video_status(conn, video.video_id, "downloaded")

    if video_path is None:
        logger.warning(
            "Áudio baixado mas vídeo falhou para {} — transcription ainda possível",
            video.video_id,
        )
    else:
        logger.info("Download completo: {}", video.video_id)

    return True


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

    audio_dir = paths["audio_dir"]
    video_dir = paths["video_dir"]

    videos: list[Video] = []
    for status in _INPUT_STATUSES:
        videos.extend(get_videos_by_status(conn, status))  # type: ignore[arg-type]

    logger.info("download: {} vídeos para baixar", len(videos))
    if not videos:
        return

    success = failed = 0
    for video in videos:
        ok = download_video_assets(
            video, conn, audio_dir, video_dir,
            dry_run=dry_run or settings.dry_run,
        )
        if ok:
            success += 1
        else:
            failed += 1

    logger.info("download concluído | ok={} falhas={}", success, failed)
