"""Implementação do PlatformClient para TikTok (fila manual).

Operações de upload copiam o arquivo para `pending_tiktok/`. Operações
que requerem a Content Posting API (update, delete, fetch_status) levantam
PlatformOperationNotSupported e registram a pendência em pendencias_tiktok.md.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from canal_soberania.core.platforms import (
    Format,
    PlatformOperationNotSupported,
    PlatformStatus,
)
from canal_soberania.logger import logger

_PENDING_DIR_DEFAULT = Path("data/clips/pending_tiktok")
_PENDENCIAS_FILE = Path("pendencias_tiktok.md")


class TikTokPlatformClient:
    """Fila manual para TikTok. upload() copia o arquivo; demais ops não suportadas."""

    platform = "tiktok"

    def __init__(self, pending_dir: Path | None = None) -> None:
        self._pending_dir = pending_dir or _PENDING_DIR_DEFAULT

    # ------------------------------------------------------------------
    # upload — fila manual
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
        """Copia o MP4 vertical para pending_tiktok/ e grava sidecar .txt."""
        if fmt != "vertical":
            raise PlatformOperationNotSupported(
                "TikTok só aceita formato vertical (9:16)"
            )
        if not clip.clip_path_vertical:
            raise ValueError(f"clip {clip.clip_id} não tem clip_path_vertical")
        src = Path(clip.clip_path_vertical)
        if not src.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {src}")

        self._pending_dir.mkdir(parents=True, exist_ok=True)
        slug = _safe_slug(title)
        dst_mp4 = self._pending_dir / f"{slug}_{clip.clip_id[:8]}.mp4"
        if not dst_mp4.exists():
            shutil.copy2(src, dst_mp4)

        hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:5])
        sidecar = f"{title}\n\n{description}\n\n{hashtags}\n"
        dst_mp4.with_suffix(".txt").write_text(sidecar, encoding="utf-8")

        logger.info("TikTokPlatformClient.upload: {} → {}", clip.clip_id, dst_mp4.name)
        return dst_mp4.stem

    # ------------------------------------------------------------------
    # Operações não suportadas — levantam exceção e registram pendência
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
        record_tiktok_pending(
            platform_id, "update_metadata",
            f"title={title!r} description={description!r} tags={tags!r}",
        )
        raise PlatformOperationNotSupported(
            "TikTok manual queue não suporta update_metadata: ver pendencias_tiktok.md"
        )

    def unschedule(self, platform_id: str) -> None:
        record_tiktok_pending(platform_id, "unschedule", "")
        raise PlatformOperationNotSupported(
            "TikTok manual queue não suporta unschedule: ver pendencias_tiktok.md"
        )

    def delete(self, platform_id: str) -> None:
        record_tiktok_pending(platform_id, "delete", "")
        raise PlatformOperationNotSupported(
            "TikTok manual queue não suporta delete: ver pendencias_tiktok.md"
        )

    def fetch_status(self, platform_ids: list[str]) -> dict[str, PlatformStatus]:
        for pid in platform_ids:
            record_tiktok_pending(pid, "fetch_status", "")
        raise PlatformOperationNotSupported(
            "TikTok manual queue não suporta fetch_status: ver pendencias_tiktok.md"
        )


def record_tiktok_pending(
    clip_id: str, operation: str, details: str, *, file: Path | None = None
) -> None:
    """Registra uma operação pendente no TikTok em pendencias_tiktok.md."""
    target = file or _PENDENCIAS_FILE
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = f"| {ts} | {clip_id} | {operation} | {details} |\n"
    try:
        with target.open("a", encoding="utf-8") as f:
            f.write(row)
    except OSError as exc:
        logger.warning("record_tiktok_pending: não foi possível gravar em {}: {}", target, exc)


def _safe_slug(text: str, max_len: int = 60) -> str:
    import re

    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "_", slug).strip("_")
    return slug[:max_len] or "clip"
