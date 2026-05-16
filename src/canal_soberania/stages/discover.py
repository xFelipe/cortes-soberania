"""Stage 1: descobre vídeos novos nos canais monitorados via YouTube Data API."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

from canal_soberania.config import Canal, Parametros, get_paths, load_canais, load_settings
from canal_soberania.db import connect, init_db, insert_video
from canal_soberania.logger import logger
from canal_soberania.models import Video


def _iso_cutoff(days_back: int) -> str:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_duration(iso_duration: str) -> int | None:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return None
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def get_uploads_playlist_id(youtube: Any, handle: str) -> str | None:
    handle_clean = handle.lstrip("@")
    try:
        resp = (
            youtube.channels()
            .list(part="contentDetails", forHandle=handle_clean)
            .execute()
        )
    except HttpError as exc:
        logger.error("YouTube API error buscando handle={}: {}", handle, exc)
        return None

    items = resp.get("items", [])
    if not items:
        logger.warning("Canal não encontrado para handle={}", handle)
        return None
    return str(items[0]["contentDetails"]["relatedPlaylists"]["uploads"])


def fetch_recent_video_ids(
    youtube: Any,
    playlist_id: str,
    cutoff_iso: str,
    max_results: int,
) -> list[str]:
    """Retorna IDs de vídeos publicados após cutoff_iso, do mais recente ao mais antigo."""
    video_ids: list[str] = []
    page_token: str | None = None

    while len(video_ids) < max_results:
        kwargs: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, max_results - len(video_ids)),
        }
        if page_token:
            kwargs["pageToken"] = page_token

        try:
            resp = youtube.playlistItems().list(**kwargs).execute()
        except HttpError as exc:
            logger.error("YouTube API error buscando playlist={}: {}", playlist_id, exc)
            break

        for item in resp.get("items", []):
            published = item["snippet"]["publishedAt"]
            if published < cutoff_iso:
                return video_ids
            video_ids.append(item["contentDetails"]["videoId"])

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def fetch_video_details(youtube: Any, video_ids: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        try:
            resp = (
                youtube.videos()
                .list(part="snippet,contentDetails,statistics", id=",".join(batch))
                .execute()
            )
        except HttpError as exc:
            logger.error("YouTube API error buscando detalhes de vídeos: {}", exc)
            continue
        results.extend(resp.get("items", []))
    return results


def discover_canal(
    youtube: Any,
    canal: Canal,
    params: Parametros,
    conn: sqlite3.Connection,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Processa um canal. Retorna (inseridos, já_existentes_ou_erros)."""
    cutoff = _iso_cutoff(params.janela_dias_discover)
    logger.info(
        "Discover {} | janela={}d | cutoff={}",
        canal.id,
        params.janela_dias_discover,
        cutoff,
    )

    playlist_id = get_uploads_playlist_id(youtube, canal.handle)
    if not playlist_id:
        return 0, 0

    video_ids = fetch_recent_video_ids(
        youtube, playlist_id, cutoff, params.max_videos_por_canal_por_run
    )
    logger.info("  {} vídeo(s) recentes encontrados para {}", len(video_ids), canal.id)

    if not video_ids:
        return 0, 0

    details = fetch_video_details(youtube, video_ids)
    inserted = 0
    skipped = 0

    for item in details:
        vid_id: str = item["id"]
        snippet: dict[str, Any] = item.get("snippet", {})
        stats: dict[str, Any] = item.get("statistics", {})
        content: dict[str, Any] = item.get("contentDetails", {})

        video = Video(
            video_id=vid_id,
            canal_id=canal.id,
            title=snippet.get("title", ""),
            description=snippet.get("description") or None,
            tags=snippet.get("tags", []),
            published_at=snippet.get("publishedAt", ""),
            duration_s=_parse_duration(content.get("duration", "")) if content.get("duration") else None,
            view_count=int(stats["viewCount"]) if "viewCount" in stats else None,
            like_count=int(stats["likeCount"]) if "likeCount" in stats else None,
            comment_count=int(stats["commentCount"]) if "commentCount" in stats else None,
        )

        if dry_run:
            logger.info("  [dry-run] {}: {}", vid_id, video.title[:80])
            inserted += 1
            continue

        try:
            cursor = conn.execute(
                "SELECT 1 FROM videos WHERE video_id = ?", (vid_id,)
            )
            already_exists = cursor.fetchone() is not None
            with conn:
                insert_video(conn, video)
            if already_exists:
                skipped += 1
            else:
                inserted += 1
                logger.debug("  Inserido {}: {}", vid_id, video.title[:60])
        except Exception as exc:
            logger.error("  Erro ao inserir {}: {}", vid_id, exc)
            skipped += 1

    return inserted, skipped


def run(
    youtube: Any | None = None,
    conn: sqlite3.Connection | None = None,
    dry_run: bool = False,
) -> None:
    """Entry point chamado pelo CLI e pelos scripts de cron."""
    settings = load_settings()
    paths = get_paths(settings)

    if conn is None:
        if not paths["db_path"].exists():
            init_db(paths["db_path"], paths["schema_path"])
        conn = connect(paths["db_path"])

    effective_dry_run = dry_run or settings.dry_run

    if not settings.youtube_api_key and youtube is None:
        logger.error("YOUTUBE_API_KEY não configurada — abortando discover")
        return

    if youtube is None:
        youtube = build("youtube", "v3", developerKey=settings.youtube_api_key)

    canais_cfg = load_canais(paths["canais_path"])
    total_inserted = 0
    total_skipped = 0

    for canal in canais_cfg.canais:
        try:
            ins, skip = discover_canal(
                youtube,
                canal,
                canais_cfg.parametros,
                conn,
                dry_run=effective_dry_run,
            )
            total_inserted += ins
            total_skipped += skip
        except Exception as exc:
            logger.error("Erro inesperado no canal {}: {}", canal.id, exc)

    logger.info(
        "Discover concluído | novos={} | já_existentes/erros={}",
        total_inserted,
        total_skipped,
    )
