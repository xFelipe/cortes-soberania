"""Estratégias concretas de upload (UploadAdapter)."""

from __future__ import annotations

import shutil
from pathlib import Path


class ManualQueueAdapter:
    """Copia o clipe para uma pasta de fila manual (TikTok/outros sem API)."""

    def __init__(self, queue_dir: Path) -> None:
        self._queue_dir = queue_dir

    @property
    def platform(self) -> str:
        return "manual_queue"

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        thumbnail_path: Path | None = None,
        publish_at: str | None = None,
    ) -> str:
        self._queue_dir.mkdir(parents=True, exist_ok=True)
        dest = self._queue_dir / video_path.name
        shutil.copy2(video_path, dest)
        meta = dest.with_suffix(".txt")
        meta.write_text(
            f"title: {title}\ndescription: {description}\ntags: {', '.join(tags)}\n",
            encoding="utf-8",
        )
        return dest.stem


class YouTubeUploadAdapter:
    """Delega ao stage upload_youtube existente — wrapper para conformidade com o protocolo."""

    @property
    def platform(self) -> str:
        return "youtube"

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        thumbnail_path: Path | None = None,
        publish_at: str | None = None,
    ) -> str:
        raise NotImplementedError(
            "YouTubeUploadAdapter requer conexão OAuth — use upload_youtube stage diretamente."
        )
