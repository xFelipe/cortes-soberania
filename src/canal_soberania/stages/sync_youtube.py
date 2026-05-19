"""Stage: sincroniza status e métricas dos clipes já enviados ao YouTube.

Chama videos.list(part="status,snippet,statistics") em lote (≤50 IDs por
chamada) para todos os clipes com youtube_id e status ativo. Atualiza:
  - youtube_privacy_status / youtube_upload_status / youtube_rejection_reason
  - youtube_actual_published_at (quando vira público)
  - youtube_view_count / like_count / comment_count
  - espelhos *_horizontal
  - status do clipe conforme as regras de transição definidas

Somente o vídeo vertical (Short) dispara mudança no campo `status` do clipe.
O horizontal só atualiza colunas informacionais.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from canal_soberania.logger import logger
from canal_soberania.models import ClipStatus
from canal_soberania.utils.youtube_auth import get_youtube_service

# Status cujos clipes devem ser incluídos na sync
_SYNC_STATUSES = (
    ClipStatus.SCHEDULED_YOUTUBE,
    ClipStatus.UPLOADING_YOUTUBE,
    ClipStatus.UPLOADED_YOUTUBE,
    ClipStatus.UNSCHEDULED_YOUTUBE,
)

_BATCH_SIZE = 50


def run(
    conn: sqlite3.Connection,
    dry_run: bool = False,
    settings: Any = None,
    paths: dict[str, Path] | None = None,
) -> None:
    """Ponto de entrada do stage (mesmo contrato dos demais stages)."""
    from canal_soberania.config import get_paths, load_settings

    if settings is None:
        settings = load_settings()
    if paths is None:
        paths = get_paths(settings)

    client_secrets = Path(settings.youtube_oauth_client_secrets_path)
    token_path = Path(settings.youtube_oauth_token_path)

    youtube = get_youtube_service(client_secrets, token_path)

    rows = _fetch_pending(conn)
    if not rows:
        logger.info("sync_youtube: nenhum clipe para sincronizar")
        return

    logger.info("sync_youtube: {} clipes a verificar", len(rows))

    # Separar IDs por orientação mantendo referência ao clip_id
    # entries: list of (clip_id, kind, youtube_id, clip_status, youtube_publish_at)
    entries: list[tuple[str, str, str, str, str | None]] = []
    for row in rows:
        if row["youtube_id"]:
            entries.append((
                row["clip_id"], "vertical",
                row["youtube_id"], row["status"], row["youtube_publish_at"],
            ))
        if row["youtube_id_horizontal"]:
            entries.append((
                row["clip_id"], "horizontal",
                row["youtube_id_horizontal"], row["status"], None,
            ))

    # Processar em batches de 50
    for i in range(0, len(entries), _BATCH_SIZE):
        batch = entries[i : i + _BATCH_SIZE]
        _process_batch(conn, youtube, batch, dry_run)

    logger.info("sync_youtube: sync concluída")


def _fetch_pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    placeholders = ",".join("?" * len(_SYNC_STATUSES))
    return conn.execute(
        f"SELECT clip_id, youtube_id, youtube_id_horizontal, status, youtube_publish_at "  # noqa: S608
        f"FROM clips "
        f"WHERE status IN ({placeholders}) "
        f"  AND (youtube_id IS NOT NULL OR youtube_id_horizontal IS NOT NULL) "
        f"ORDER BY youtube_last_synced_at NULLS FIRST",
        _SYNC_STATUSES,
    ).fetchall()


def _process_batch(  # noqa: C901
    conn: sqlite3.Connection,
    youtube: Any,
    batch: list[tuple[str, str, str, str, str | None]],
    dry_run: bool,
) -> None:
    id_map: dict[str, list[tuple[str, str, str, str | None]]] = {}
    for clip_id, kind, yt_id, clip_status, publish_at in batch:
        id_map.setdefault(yt_id, []).append((clip_id, kind, clip_status, publish_at))

    resp = youtube.videos().list(
        part="status,snippet,statistics",
        id=",".join(id_map.keys()),
    ).execute()

    returned_ids = {item["id"] for item in resp.get("items", [])}
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Itens retornados — atualiza colunas e transiciona status
    for item in resp.get("items", []):
        yt_id = item["id"]
        for clip_id, kind, clip_status, scheduled_publish_at in id_map[yt_id]:
            _apply_item(conn, youtube, clip_id, kind, clip_status,
                        scheduled_publish_at, item, now_iso, dry_run)

    # IDs que não voltaram = vídeo deletado do canal
    for yt_id, entries in id_map.items():
        if yt_id in returned_ids:
            continue
        for clip_id, kind, clip_status, _ in entries:
            if kind == "vertical":
                logger.warning("sync_youtube: {} | {} não encontrado — marcando deleted_youtube",
                               clip_id, yt_id)
                if not dry_run:
                    _transition(conn, clip_id, clip_status, ClipStatus.DELETED_YOUTUBE)
                    _update_cols(conn, clip_id, {
                        "youtube_upload_status": "deleted",
                        "youtube_last_synced_at": now_iso,
                    })
            else:
                # Horizontal deletado: limpa ID mas não muda status principal
                logger.info("sync_youtube: {} | horizontal {} deletado (sem mudança de status)",
                            clip_id, yt_id)
                if not dry_run:
                    _update_cols(conn, clip_id, {
                        "youtube_id_horizontal": None,
                        "youtube_upload_status_horizontal": "deleted",
                        "youtube_last_synced_at": now_iso,
                    })

    if not dry_run:
        conn.commit()


def _apply_item(
    conn: sqlite3.Connection,
    youtube: Any,
    clip_id: str,
    kind: str,
    clip_status: str,
    scheduled_publish_at: str | None,
    item: dict[str, Any],
    now_iso: str,
    dry_run: bool,
) -> None:
    status_data = item.get("status", {})
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})

    privacy = status_data.get("privacyStatus", "")
    upload_status = status_data.get("uploadStatus", "")
    publish_at_yt = status_data.get("publishAt")        # presente quando ainda agendado
    rejection_reason = status_data.get("rejectionReason")
    actual_published_at = snippet.get("publishedAt")    # quando virou público

    view_count = _int_or_none(stats.get("viewCount"))
    like_count = _int_or_none(stats.get("likeCount"))
    comment_count = _int_or_none(stats.get("commentCount"))

    if kind == "horizontal":
        cols: dict[str, Any] = {
            "youtube_privacy_status_horizontal": privacy,
            "youtube_upload_status_horizontal": upload_status,
            "youtube_view_count_horizontal": view_count,
            "youtube_like_count_horizontal": like_count,
            "youtube_comment_count_horizontal": comment_count,
            "youtube_last_synced_at": now_iso,
        }
        if not dry_run:
            _update_cols(conn, clip_id, cols)
        return

    # --- Vertical: decide transição de status ---
    cols = {
        "youtube_privacy_status": privacy,
        "youtube_upload_status": upload_status,
        "youtube_view_count": view_count,
        "youtube_like_count": like_count,
        "youtube_comment_count": comment_count,
        "youtube_last_synced_at": now_iso,
    }

    new_status: str | None = None

    if upload_status == "rejected":
        new_status = ClipStatus.REJECTED_YOUTUBE
        cols["youtube_rejection_reason"] = rejection_reason
        logger.warning("sync_youtube: {} rejeitado pelo YouTube | motivo={}", clip_id, rejection_reason)

    elif privacy == "public" and not publish_at_yt:
        # Publicou de verdade
        if clip_status != ClipStatus.UPLOADED_YOUTUBE:
            new_status = ClipStatus.UPLOADED_YOUTUBE
        cols["youtube_actual_published_at"] = actual_published_at
        logger.info("sync_youtube: {} publicado | views={}", clip_id, view_count)

    elif privacy == "private" and not publish_at_yt and clip_status in (ClipStatus.SCHEDULED_YOUTUBE, ClipStatus.UPLOADING_YOUTUBE):
        # Era agendado mas publishAt sumiu sem virar público = desagendado
        new_status = ClipStatus.UNSCHEDULED_YOUTUBE
        logger.warning("sync_youtube: {} desagendado (publishAt removido)", clip_id)

    elif privacy == "private" and publish_at_yt and publish_at_yt != scheduled_publish_at:
        # Reagendado — atualiza a data sem mudar status
        cols["youtube_publish_at"] = publish_at_yt
        logger.info("sync_youtube: {} reagendado → {}", clip_id, publish_at_yt)

    else:
        logger.debug("sync_youtube: {} sem mudança | privacy={} upload={}", clip_id, privacy, upload_status)

    if not dry_run:
        if new_status:
            _transition(conn, clip_id, clip_status, new_status)
        _update_cols(conn, clip_id, cols)


def _transition(conn: sqlite3.Connection, clip_id: str, current: str, new: str) -> None:
    from canal_soberania.core.state import ClipStateMachine

    try:
        ClipStateMachine.transition(clip_id, current, new)  # type: ignore[arg-type]
        conn.execute(
            "UPDATE clips SET status = ?, updated_at = datetime('now') WHERE clip_id = ?",
            (new, clip_id),
        )
    except Exception as exc:
        logger.error("sync_youtube: falha ao transicionar {} {} → {}: {}", clip_id, current, new, exc)


def _update_cols(conn: sqlite3.Connection, clip_id: str, cols: dict[str, Any]) -> None:
    if not cols:
        return
    assignments = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(
        f"UPDATE clips SET {assignments}, updated_at = datetime('now') WHERE clip_id = ?",  # noqa: S608
        (*cols.values(), clip_id),
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None
