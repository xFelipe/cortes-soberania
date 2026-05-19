"""Router: /inbox — lista priorizada para a tela principal da UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from canal_soberania.api.auth import verify_token
from canal_soberania.api.deps import get_service
from canal_soberania.models import ClipStatus, VideoStatus
from canal_soberania.services.pipeline_service import PipelineService

router = APIRouter(prefix="/inbox", tags=["inbox"])

# Status que aparecem na Inbox (em ordem de prioridade)
_CLIP_INBOX_STATUSES = [ClipStatus.METADATA_READY]
_VIDEO_INBOX_STATUSES = [
    VideoStatus.DISCOVERED,
    VideoStatus.PROCESSING_ERROR,
    VideoStatus.TRANSCRIBE_ERROR,
]


@router.get("")
def get_inbox(
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, Any]:
    """Retorna itens priorizados para revisão pelo operador."""
    clips_ready = [
        {"type": "clip", "priority": 1, **c.model_dump()}
        for c in service.get_clips(status=ClipStatus.METADATA_READY)
    ]
    videos_new = [
        {"type": "video", "priority": 2, **v.model_dump()}
        for v in service.get_videos(status=VideoStatus.DISCOVERED)
    ]
    videos_error = [
        {"type": "video", "priority": 3, **v.model_dump()}
        for v in service.get_videos(status=VideoStatus.PROCESSING_ERROR)
    ]

    items = clips_ready + videos_new + videos_error
    return {"items": items, "total": len(items)}
