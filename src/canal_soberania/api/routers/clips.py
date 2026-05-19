"""Router: /clips"""

from __future__ import annotations

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from canal_soberania.api.auth import verify_token
from canal_soberania.api.deps import get_service
from canal_soberania.models import Clip, ClipStatus
from canal_soberania.services.pipeline_service import PipelineService

router = APIRouter(prefix="/clips", tags=["clips"])


class ClipPatchBody(BaseModel):
    hook: str | None = None
    payoff: str | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    youtube_publish_at: str | None = None
    render_vertical: bool = True
    render_horizontal: bool = True


class TrimBody(BaseModel):
    start_s: Annotated[float, Field(ge=0.0)]
    end_s: Annotated[float, Field(ge=0.0)]


@router.get("", response_model=list[Clip])
def list_clips(
    status: ClipStatus | None = None,
    video_id: str | None = None,
    limit: int = 200,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> list[Clip]:
    clips = service.get_clips(status=status)
    if video_id:
        clips = [c for c in clips if c.video_id == video_id]
    return clips[:limit]


@router.get("/{clip_id}", response_model=Clip)
def get_clip(
    clip_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> Clip:
    clip = service.get_clip(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    return clip


@router.post("/{clip_id}/approve")
def approve_clip(
    clip_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    """Aprova o clipe e dispara upload YouTube em background."""
    clip = service.get_clip(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    if clip.status != ClipStatus.METADATA_READY:
        raise HTTPException(
            status_code=400,
            detail=f"Clipe não está em METADATA_READY: {clip.status}",
        )
    thread = threading.Thread(
        target=service.run_upload_youtube,
        kwargs={"dry_run": False},
        daemon=True,
        name=f"upload-{clip_id}",
    )
    thread.start()
    return {"status": "upload_started", "clip_id": clip_id}


@router.post("/{clip_id}/reject")
def reject_clip(
    clip_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    clip = service.get_clip(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    service._clip_repo.update_status(clip_id, ClipStatus.REJECTED_YOUTUBE)  # noqa: SLF001
    return {"status": "rejected", "clip_id": clip_id}


@router.post("/{clip_id}/trim")
def trim_clip(
    clip_id: str,
    body: TrimBody,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, object]:
    if body.end_s <= body.start_s:
        raise HTTPException(status_code=400, detail="end_s deve ser maior que start_s")
    clip = service.get_clip(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    service._clip_repo.update_trim(clip_id, body.start_s, body.end_s)  # noqa: SLF001
    return {"status": "trimmed", "clip_id": clip_id, "start_s": body.start_s, "end_s": body.end_s}


@router.delete("/{clip_id}")
def discard_clip(
    clip_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    """Remove o clipe do banco de dados (ação irreversível)."""
    clip = service.get_clip(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    service._clip_repo.delete(clip_id)  # noqa: SLF001
    return {"status": "discarded", "clip_id": clip_id}


@router.patch("/{clip_id}")
def update_clip(
    clip_id: str,
    body: ClipPatchBody,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    clip = service.get_clip(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    service.update_clip_text(
        clip_id=clip_id,
        hook=body.hook,
        payoff=body.payoff,
        title=body.title,
        description=body.description,
        tags=body.tags,
        youtube_publish_at=body.youtube_publish_at,
        render_vertical=body.render_vertical,
        render_horizontal=body.render_horizontal,
    )
    return {"status": "updated", "clip_id": clip_id}
