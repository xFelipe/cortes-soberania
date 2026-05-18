"""Protocolo abstrato para plataformas de distribuição de clipes.

Implementações concretas: platforms/youtube.py, platforms/tiktok.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from canal_soberania.config import Settings
    from canal_soberania.models import Clip

Format = Literal["vertical", "horizontal"]


class PlatformOperationNotSupported(Exception):
    """Operação não suportada pela plataforma (ex.: TikTok manual delete)."""


@dataclass
class PlatformStatus:
    privacy_status: str | None = None
    upload_status: str | None = None
    publish_at: str | None = None
    actual_published_at: str | None = None
    rejection_reason: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None


@runtime_checkable
class PlatformClient(Protocol):
    """Interface para operações de upload e gestão de clipes em plataformas externas."""

    @property
    def platform(self) -> str: ...

    def upload(
        self,
        clip: Clip,
        fmt: Format,
        *,
        title: str,
        description: str,
        tags: list[str],
        publish_at: str | None,
        thumb_path: Path | None,
    ) -> str:
        """Faz upload de um clipe; retorna o ID gerado pela plataforma."""
        ...

    def update_metadata(
        self,
        platform_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        publish_at: str | None = None,
    ) -> None:
        """Atualiza metadados de um vídeo já enviado."""
        ...

    def unschedule(self, platform_id: str) -> None:
        """Remove agendamento: vídeo volta a ser privado sem data de publicação."""
        ...

    def delete(self, platform_id: str) -> None:
        """Deleta o vídeo da plataforma permanentemente."""
        ...

    def fetch_status(
        self, platform_ids: list[str]
    ) -> dict[str, PlatformStatus]:
        """Consulta status e métricas para uma lista de IDs. Retorna mapa id → status."""
        ...


def get_platform(
    name: Literal["youtube", "tiktok"],
    settings: Settings,
) -> PlatformClient:
    """Factory — retorna instância do PlatformClient configurado para a plataforma."""
    if name == "youtube":
        from canal_soberania.platforms.youtube import YouTubePlatformClient

        return YouTubePlatformClient(
            client_secrets_path=Path(settings.youtube_oauth_client_secrets_path),
            token_path=Path(settings.youtube_oauth_token_path),
        )
    if name == "tiktok":
        from canal_soberania.platforms.tiktok import TikTokPlatformClient

        return TikTokPlatformClient()
    raise ValueError(f"Plataforma desconhecida: {name}")
