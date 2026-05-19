"""Stage 4: baixa áudio (MP3) e vídeo (MP4 1080p) via yt-dlp."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import yt_dlp
import yt_dlp.utils as ydl_utils
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from canal_soberania.config import get_paths, load_settings
from canal_soberania.db import (
    connect,
    get_videos_by_status,
    init_db,
    update_video_paths,
    update_video_status,
)
from canal_soberania.logger import logger
from canal_soberania.models import Video, VideoStatus

# Statuses que entram no stage de download (inclui DOWNLOADING para recovery de orphans)
_INPUT_STATUSES = (VideoStatus.TRIAGE_CAPTION_PASSED, VideoStatus.TRIAGE_CAPTION_SKIPPED, VideoStatus.DOWNLOADING)

_MIN_VALID_BYTES = 10_240  # 10 KB — arquivos menores são provavelmente parciais


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
        "retries": 10,
        "fragment_retries": 10,
        "retry_sleep_functions": {"http": lambda n: min(4 * 2**n, 60)},
        "socket_timeout": 30,
    }


def _ydl_video_opts(dest_path: Path) -> dict[str, Any]:
    return {
        "format": (
            "bestvideo[height<=1080][ext=mp4][vcodec!^=av01]+bestaudio[ext=m4a]"
            "/bestvideo[height<=1080][vcodec!^=av01]+bestaudio"
            "/bestvideo[height<=1080]+bestaudio"
            "/best[height<=1080]/best"
        ),
        "outtmpl": str(dest_path),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "retries": 10,
        "fragment_retries": 10,
        "retry_sleep_functions": {"http": lambda n: min(4 * 2**n, 60)},
        "socket_timeout": 30,
    }


@retry(
    retry=retry_if_exception_type(ydl_utils.DownloadError),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _ydl_download(opts: dict[str, Any], url: str) -> None:
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


def download_audio(video_id: str, audio_dir: Path, dry_run: bool = False) -> Path | None:
    """Baixa áudio como MP3. Retorna o path do arquivo ou None em caso de erro."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    dest = audio_dir / f"{video_id}.mp3"

    if dest.exists() and dest.stat().st_size >= _MIN_VALID_BYTES:
        logger.debug("Áudio já existe: {}", dest)
        return dest

    if dest.exists():
        logger.warning("Áudio existente parece corrompido ({} bytes), re-baixando", dest.stat().st_size)
        dest.unlink()

    if dry_run:
        logger.info("[dry-run] download_audio {}", video_id)
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = _ydl_audio_opts(audio_dir / video_id)

    try:
        _ydl_download(opts, url)
    except Exception as exc:
        logger.error("yt-dlp audio error {}: {}", video_id, exc)
        return None

    if not dest.exists() or dest.stat().st_size < _MIN_VALID_BYTES:
        logger.error("Áudio baixado mas inválido: {}", dest)
        return None

    return dest


def download_video(video_id: str, video_dir: Path, dry_run: bool = False) -> Path | None:
    """Baixa vídeo em até 1080p como MP4. Retorna o path ou None em caso de erro."""
    video_dir.mkdir(parents=True, exist_ok=True)
    dest = video_dir / f"{video_id}.mp4"

    if dest.exists() and dest.stat().st_size >= _MIN_VALID_BYTES:
        logger.debug("Vídeo já existe: {}", dest)
        return dest

    if dest.exists():
        logger.warning("Vídeo existente parece corrompido ({} bytes), re-baixando", dest.stat().st_size)
        dest.unlink()

    if dry_run:
        logger.info("[dry-run] download_video {}", video_id)
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = _ydl_video_opts(dest)

    try:
        _ydl_download(opts, url)
    except Exception as exc:
        logger.error("yt-dlp video error {}: {}", video_id, exc)
        return None

    if not dest.exists() or dest.stat().st_size < _MIN_VALID_BYTES:
        logger.error("Vídeo baixado mas inválido: {}", dest)
        return None

    return dest


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
    from canal_soberania.utils.heartbeat import HeartbeatKeeper

    if not dry_run:
        with conn:
            update_video_status(conn, video.video_id, VideoStatus.DOWNLOADING)

    with HeartbeatKeeper(conn, "videos", "video_id", video.video_id):
        audio_path = download_audio(video.video_id, audio_dir, dry_run=dry_run)
        video_path = download_video(video.video_id, video_dir, dry_run=dry_run)

    if dry_run:
        return True

    if audio_path is None:
        logger.error("Falha no download de áudio para {}", video.video_id)
        with conn:
            update_video_status(
                conn, video.video_id, VideoStatus.PROCESSING_ERROR, "audio_download_failed"
            )
        return False

    with conn:
        update_video_paths(
            conn,
            video.video_id,
            audio_path=str(audio_path),
            video_path=str(video_path) if video_path else None,
        )
        update_video_status(conn, video.video_id, VideoStatus.DOWNLOADED)

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
        videos.extend(get_videos_by_status(conn, status))

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
