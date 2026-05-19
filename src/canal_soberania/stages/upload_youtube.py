"""Stage 11: faz upload de clipes para o YouTube (privado, agendado)."""

from __future__ import annotations

import json
import socket
import sqlite3
import ssl
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from canal_soberania.config import get_paths, load_settings
from canal_soberania.db import connect, get_clips_by_status, init_db
from canal_soberania.logger import logger
from canal_soberania.models import Clip, ClipStatus

_INPUT_STATUS: ClipStatus = ClipStatus.METADATA_READY
_UPLOADING_STATUS: ClipStatus = ClipStatus.UPLOADING_YOUTUBE
# Clipes em scheduled_youtube com render_flag=True mas sem ID → novo formato a enviar
_REUPLOAD_STATUS: ClipStatus = ClipStatus.SCHEDULED_YOUTUBE

_RETRIABLE_HTTP_STATUS = {500, 502, 503, 504}
_RETRIABLE_EXCEPTIONS = (socket.error, ssl.SSLError, ConnectionError, TimeoutError)

# Horários de publicação (UTC-3 = horário de Brasília)
_PUBLISH_HOURS_BRT = [9, 14, 19]
_MAX_UPLOADS_PER_DAY = 3


def _get_youtube_service(client_secrets_path: Path, token_path: Path) -> object:
    from canal_soberania.utils.youtube_auth import get_youtube_service
    return get_youtube_service(client_secrets_path, token_path)


def _next_publish_slot(
    conn: sqlite3.Connection,
    max_per_day: int = _MAX_UPLOADS_PER_DAY,
    publish_hours_brt: list[int] = _PUBLISH_HOURS_BRT,
) -> datetime:
    """
    Calcula o próximo horário de publicação disponível.
    Respeita o limite max_per_day e os horários de pico.
    Retorna datetime UTC.
    """
    brt_offset = timezone(timedelta(hours=-3))
    now_brt = datetime.now(brt_offset)
    today_brt = now_brt.date()

    # Conta uploads já agendados por dia
    rows = conn.execute(
        "SELECT youtube_publish_at FROM clips WHERE youtube_publish_at IS NOT NULL"
    ).fetchall()

    scheduled_by_day: dict[str, int] = {}
    for row in rows:
        if row["youtube_publish_at"]:
            try:
                dt = datetime.fromisoformat(row["youtube_publish_at"])
                day = dt.astimezone(brt_offset).date().isoformat()
                scheduled_by_day[day] = scheduled_by_day.get(day, 0) + 1
            except ValueError:
                pass

    # Procura o primeiro slot disponível a partir de hoje
    candidate_day = today_brt
    for _ in range(30):  # tenta até 30 dias à frente
        day_str = candidate_day.isoformat()
        slots_used = scheduled_by_day.get(day_str, 0)
        if slots_used < max_per_day:
            # Pega o próximo horário disponível no dia
            for hour in sorted(publish_hours_brt):
                slot_brt = datetime(
                    candidate_day.year,
                    candidate_day.month,
                    candidate_day.day,
                    hour,
                    0,
                    0,
                    tzinfo=brt_offset,
                )
                if slot_brt > now_brt:
                    # Conta se este slot específico já está tomado
                    slots_at_hour = sum(
                        1
                        for row in rows
                        if row["youtube_publish_at"]
                        and _slot_matches(row["youtube_publish_at"], candidate_day, hour, brt_offset)
                    )
                    if slots_at_hour == 0:
                        return slot_brt.astimezone(UTC)
        candidate_day = candidate_day + timedelta(days=1)

    # Fallback improvável: amanhã às 9h BRT
    tomorrow = today_brt + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, tzinfo=brt_offset).astimezone(
        UTC
    )


def _slot_matches(
    iso_str: str,
    target_day: object,
    target_hour: int,
    brt_offset: timezone,
) -> bool:
    try:
        dt = datetime.fromisoformat(iso_str).astimezone(brt_offset)

        return dt.date() == target_day and dt.hour == target_hour
    except ValueError:
        return False


def _do_upload(
    youtube: object,
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    publish_at_iso: str,
    is_short: bool = False,
) -> str:
    """Executa o upload de um arquivo de vídeo e retorna o youtube_id."""
    from googleapiclient.errors import HttpError as GApiHttpError
    from googleapiclient.http import MediaFileUpload

    full_title = f"#Shorts {title[:93]}" if is_short else title[:100]
    body = {
        "snippet": {
            "title": full_title,
            "description": description,
            "tags": tags,
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at_iso,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(  # type: ignore[attr-defined]
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retry_count = 0
    max_retries = 5
    while response is None:
        try:
            _, response = request.next_chunk()
        except GApiHttpError as exc:
            if exc.resp.status in _RETRIABLE_HTTP_STATUS and retry_count < max_retries:
                retry_count += 1
                wait = min(2**retry_count, 30)
                logger.warning(
                    "upload chunk HTTP {}, retry {}/{} em {}s",
                    exc.resp.status, retry_count, max_retries, wait,
                )
                time.sleep(wait)
            else:
                raise
        except _RETRIABLE_EXCEPTIONS as exc:
            if retry_count < max_retries:
                retry_count += 1
                wait = min(2**retry_count, 30)
                logger.warning(
                    "upload chunk erro de rede: {}, retry {}/{} em {}s",
                    exc, retry_count, max_retries, wait,
                )
                time.sleep(wait)
            else:
                raise

    return str(response["id"])


def upload_clip(  # noqa: C901
    clip: Clip,
    conn: sqlite3.Connection,
    client_secrets_path: Path,
    token_path: Path,
    dry_run: bool = False,
) -> str | None:
    """
    Faz upload de um clipe para o YouTube.
    - vertical (9:16) → Short (privado agendado), youtube_id
    - horizontal (16:9) → vídeo regular (privado agendado), youtube_id_horizontal
    Retorna o youtube_id do Short, ou None em caso de falha.
    """
    existing = conn.execute(
        "SELECT youtube_id, youtube_id_horizontal FROM clips WHERE clip_id = ?",
        (clip.clip_id,),
    ).fetchone()
    vertical_done = existing and existing["youtube_id"]
    horizontal_done = existing and existing["youtube_id_horizontal"]

    if vertical_done and horizontal_done:
        logger.info(
            "upload_youtube: clip {} já tem youtube_id={} e horizontal={}, pulando",
            clip.clip_id, existing["youtube_id"], existing["youtube_id_horizontal"],
        )
        return str(existing["youtube_id"])

    if not clip.clip_path_vertical:
        logger.warning("upload_youtube: sem clip_path_vertical para {}", clip.clip_id)
        return None

    vertical_path = Path(clip.clip_path_vertical)
    horizontal_path = Path(clip.clip_path_horizontal) if clip.clip_path_horizontal else None

    if not vertical_path.exists():
        logger.warning("upload_youtube: arquivo vertical não encontrado: {}", vertical_path)
        return None

    title = clip.title or clip.hook or clip.clip_id
    description = clip.description or ""
    tags_raw = clip.tags or "[]"
    try:
        tags: list[str] = json.loads(tags_raw) if isinstance(tags_raw, str) else list(tags_raw)
    except (json.JSONDecodeError, TypeError):
        tags = []

    publish_at = _next_publish_slot(conn)
    publish_at_iso = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    # Horizontal publica 1h depois do Short para evitar conflito de slot
    from datetime import timedelta
    publish_at_h = publish_at + timedelta(hours=1)
    publish_at_h_iso = publish_at_h.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    if dry_run:
        logger.info(
            "[dry-run] upload_youtube clip={} short_title={!r} publish_at={} | horizontal publish_at={}",
            clip.clip_id, f"#Shorts {title[:40]}", publish_at_iso, publish_at_h_iso,
        )
        return None

    try:
        youtube = _get_youtube_service(client_secrets_path, token_path)
    except Exception as exc:
        logger.error("upload_youtube: falha na autenticação: {}", exc)
        return None

    # Marca status intermediário para recovery em caso de crash
    with conn:
        conn.execute(
            "UPDATE clips SET status=? WHERE clip_id=?",
            (_UPLOADING_STATUS, clip.clip_id),
        )

    try:
        youtube_id: str | None = None
        youtube_id_h: str | None = None

        # 1. Upload vertical → Short
        if not vertical_done:
            youtube_id = _do_upload(
                youtube, vertical_path, title, description, tags,
                publish_at_iso, is_short=True,
            )
            logger.info("upload_youtube Short: clip={} → {}", clip.clip_id, youtube_id)
            with conn:
                conn.execute(
                    "UPDATE clips SET youtube_id=?, youtube_publish_at=? WHERE clip_id=?",
                    (youtube_id, publish_at_iso, clip.clip_id),
                )
                conn.execute(
                    "INSERT INTO uploads_log (clip_id, platform, status, platform_id) VALUES (?, 'youtube_short', 'success', ?)",
                    (clip.clip_id, youtube_id),
                )
        else:
            youtube_id = str(existing["youtube_id"])

        # 2. Upload horizontal → vídeo regular
        if not horizontal_done and horizontal_path and horizontal_path.exists():
            youtube_id_h = _do_upload(
                youtube, horizontal_path, title, description, tags,
                publish_at_h_iso, is_short=False,
            )
            logger.info("upload_youtube horizontal: clip={} → {}", clip.clip_id, youtube_id_h)
            with conn:
                conn.execute(
                    "UPDATE clips SET youtube_id_horizontal=?, youtube_publish_at_horizontal=? WHERE clip_id=?",
                    (youtube_id_h, publish_at_h_iso, clip.clip_id),
                )
                conn.execute(
                    "INSERT INTO uploads_log (clip_id, platform, status, platform_id) VALUES (?, 'youtube_horizontal', 'success', ?)",
                    (clip.clip_id, youtube_id_h),
                )
        elif not horizontal_done:
            logger.warning("upload_youtube: sem clip_path_horizontal para {}, pulando vídeo regular", clip.clip_id)

        with conn:
            conn.execute(
                "UPDATE clips SET status=? WHERE clip_id=?",
                (ClipStatus.SCHEDULED_YOUTUBE, clip.clip_id),
            )

        return youtube_id

    except Exception as exc:
        logger.error("upload_youtube: erro no upload de {}: {}", clip.clip_id, exc)
        # Se estava em scheduled_youtube (re-upload), volta para scheduled (não perde status)
        rollback_status = ClipStatus.SCHEDULED_YOUTUBE if clip.status == ClipStatus.SCHEDULED_YOUTUBE else ClipStatus.METADATA_READY
        with conn:
            conn.execute(
                "UPDATE clips SET status=?, error_message=? WHERE clip_id=?",
                (rollback_status, str(exc), clip.clip_id),
            )
            conn.execute(
                "INSERT INTO uploads_log (clip_id, platform, status, error_message) VALUES (?, 'youtube', 'error', ?)",
                (clip.clip_id, str(exc)),
            )
        return None


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

    client_secrets_path = Path(settings.youtube_oauth_client_secrets_path)
    token_path = Path(settings.youtube_oauth_token_path)

    if not dry_run and not client_secrets_path.exists():
        logger.error(
            "upload_youtube: client_secrets não encontrado em {}. "
            "Crie via Google Cloud Console (OAuth 2.0) e configure YOUTUBE_OAUTH_CLIENT_SECRETS_PATH.",
            client_secrets_path,
        )
        return

    # Inclui uploading_youtube (orphans de crash) e scheduled_youtube com formato pendente
    scheduled_all = get_clips_by_status(conn, _REUPLOAD_STATUS)
    scheduled_pending = [
        c for c in scheduled_all
        if (c.render_vertical and not c.youtube_id)
        or (c.render_horizontal and not c.youtube_id_horizontal and c.clip_path_horizontal)
    ]
    clips = (
        get_clips_by_status(conn, _INPUT_STATUS)
        + get_clips_by_status(conn, _UPLOADING_STATUS)
        + scheduled_pending
    )
    logger.info("upload_youtube: {} clipes para processar", len(clips))

    success = failed = 0
    for clip in clips:
        result = upload_clip(
            clip=clip,
            conn=conn,
            client_secrets_path=client_secrets_path,
            token_path=token_path,
            dry_run=dry_run or settings.dry_run,
        )
        if result is not None or (dry_run or settings.dry_run):
            success += 1
        else:
            failed += 1

    logger.info("upload_youtube concluído | ok={} falhas={}", success, failed)
