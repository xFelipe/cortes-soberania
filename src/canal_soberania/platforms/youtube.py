"""Implementação concreta do PlatformClient para o YouTube Data API v3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from canal_soberania.core.platforms import Format, PlatformStatus
from canal_soberania.logger import logger

_BATCH_SIZE = 50


class YouTubePlatformClient:
    """Operações de upload, edição e remoção de vídeos no YouTube."""

    platform = "youtube"

    def __init__(self, client_secrets_path: Path, token_path: Path) -> None:
        self._client_secrets_path = client_secrets_path
        self._token_path = token_path
        self._svc: Any = None  # lazy init

    def _get_service(self) -> Any:
        if self._svc is None:
            from canal_soberania.utils.youtube_auth import get_youtube_service

            self._svc = get_youtube_service(self._client_secrets_path, self._token_path)
        return self._svc

    # ------------------------------------------------------------------
    # upload
    # ------------------------------------------------------------------

    def upload(
        self,
        clip: Any,  # Clip
        fmt: Format,
        *,
        title: str,
        description: str,
        tags: list[str],
        publish_at: str | None,
        thumb_path: Path | None,
    ) -> str:
        """Faz upload de um arquivo de vídeo e retorna o YouTube ID."""
        from canal_soberania.stages.upload_youtube import _do_upload

        if fmt == "vertical":
            if not clip.clip_path_vertical:
                raise ValueError(f"clip {clip.clip_id} não tem clip_path_vertical")
            video_path = Path(clip.clip_path_vertical)
            is_short = True
            full_title = f"#Shorts {title[:93]}"
        else:
            if not clip.clip_path_horizontal:
                raise ValueError(f"clip {clip.clip_id} não tem clip_path_horizontal")
            video_path = Path(clip.clip_path_horizontal)
            is_short = False
            full_title = title[:100]

        if not video_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {video_path}")

        if publish_at is None:
            raise ValueError("publish_at é obrigatório para upload no YouTube")

        youtube = self._get_service()
        yt_id = _do_upload(
            youtube,
            video_path,
            full_title,
            description,
            tags,
            publish_at,
            is_short=is_short,
        )
        logger.info("YouTubePlatformClient.upload: {} ({}) → {}", clip.clip_id, fmt, yt_id)
        return yt_id

    # ------------------------------------------------------------------
    # update_metadata
    # ------------------------------------------------------------------

    def update_metadata(
        self,
        platform_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        publish_at: str | None = None,
    ) -> None:
        """Atualiza metadados de um vídeo já enviado (GET + selective PATCH)."""
        youtube = self._get_service()

        # GET current data to preserve unmodified fields
        resp = youtube.videos().list(
            part="snippet,status",
            id=platform_id,
        ).execute()
        items = resp.get("items", [])
        if not items:
            raise ValueError(f"Vídeo {platform_id} não encontrado no YouTube")
        item = items[0]

        body: dict[str, Any] = {"id": platform_id}
        parts: list[str] = []

        if title is not None or description is not None or tags is not None:
            cur_snippet = item["snippet"]
            update_snippet: dict[str, Any] = {
                "title": title if title is not None else cur_snippet.get("title", ""),
                "description": description
                if description is not None
                else cur_snippet.get("description", ""),
                "tags": tags if tags is not None else cur_snippet.get("tags", []),
                "categoryId": cur_snippet.get("categoryId", "22"),
            }
            if cur_snippet.get("defaultLanguage"):
                update_snippet["defaultLanguage"] = cur_snippet["defaultLanguage"]
            body["snippet"] = update_snippet
            parts.append("snippet")

        if publish_at is not None:
            cur_status = item.get("status", {})
            update_status: dict[str, Any] = {
                "privacyStatus": cur_status.get("privacyStatus", "private"),
                "publishAt": publish_at,
                "selfDeclaredMadeForKids": cur_status.get("selfDeclaredMadeForKids", False),
            }
            body["status"] = update_status
            parts.append("status")

        if not parts:
            return

        youtube.videos().update(
            part=",".join(parts),
            body=body,
        ).execute()
        logger.info("YouTubePlatformClient.update_metadata: {}", platform_id)

    # ------------------------------------------------------------------
    # unschedule
    # ------------------------------------------------------------------

    def unschedule(self, platform_id: str) -> None:
        """Remove o agendamento: vídeo volta a ser privado sem publishAt."""
        youtube = self._get_service()
        youtube.videos().update(
            part="status",
            body={
                "id": platform_id,
                "status": {
                    "privacyStatus": "private",
                    "selfDeclaredMadeForKids": False,
                },
            },
        ).execute()
        logger.info("YouTubePlatformClient.unschedule: {}", platform_id)

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def delete(self, platform_id: str) -> None:
        """Deleta o vídeo do canal permanentemente."""
        youtube = self._get_service()
        youtube.videos().delete(id=platform_id).execute()
        logger.info("YouTubePlatformClient.delete: {}", platform_id)

    # ------------------------------------------------------------------
    # fetch_status
    # ------------------------------------------------------------------

    def fetch_status(self, platform_ids: list[str]) -> dict[str, PlatformStatus]:
        """Consulta status e métricas em lote (≤50 IDs por chamada)."""
        if not platform_ids:
            return {}
        youtube = self._get_service()
        result: dict[str, PlatformStatus] = {}

        for i in range(0, len(platform_ids), _BATCH_SIZE):
            batch = platform_ids[i : i + _BATCH_SIZE]
            resp = youtube.videos().list(
                part="status,snippet,statistics",
                id=",".join(batch),
            ).execute()
            for item in resp.get("items", []):
                result[item["id"]] = _parse_platform_status(item)

        return result


def _parse_platform_status(item: dict[str, Any]) -> PlatformStatus:
    status_data = item.get("status", {})
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})
    return PlatformStatus(
        privacy_status=status_data.get("privacyStatus"),
        upload_status=status_data.get("uploadStatus"),
        publish_at=status_data.get("publishAt"),
        actual_published_at=snippet.get("publishedAt"),
        rejection_reason=status_data.get("rejectionReason"),
        view_count=_int_or_none(stats.get("viewCount")),
        like_count=_int_or_none(stats.get("likeCount")),
        comment_count=_int_or_none(stats.get("commentCount")),
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None
