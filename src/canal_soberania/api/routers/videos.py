"""Router: /videos"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from canal_soberania.api.auth import verify_token
from canal_soberania.api.deps import get_service
from canal_soberania.models import Video, VideoStatus
from canal_soberania.services.pipeline_service import PipelineService

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("", response_model=list[Video])
def list_videos(
    status: VideoStatus | None = None,
    limit: int = 200,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> list[Video]:
    videos = service.get_videos(status=status)
    return videos[:limit]


@router.get("/{video_id}", response_model=Video)
def get_video(
    video_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> Video:
    video = service.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")
    return video


@router.post("/{video_id}/approve")
def approve_video(
    video_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    try:
        service.approve_video(video_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "video_id": video_id}


@router.post("/{video_id}/reject")
def reject_video(
    video_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    try:
        service.reject_video(video_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "video_id": video_id}
