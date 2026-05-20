"""Router: /clips"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
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
    score_viral: int | None = None


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
        score_viral=body.score_viral,
    )
    return {"status": "updated", "clip_id": clip_id}


class FaceCropResponse(BaseModel):
    crop_x: int
    crop_width: int
    source_width: int
    source_height: int


@router.get("/{clip_id}/face-crop", response_model=FaceCropResponse)
def get_face_crop(
    clip_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> FaceCropResponse:
    """Detecta posição do rosto no vídeo-fonte e retorna coordenadas do crop 9:16."""
    clip = service.get_clip(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")

    video = service.get_video(clip.video_id)
    if video is None or not video.video_path:
        raise HTTPException(status_code=404, detail="Vídeo-fonte não disponível")

    video_path = Path(video.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo de vídeo não encontrado")

    # Detecta dimensões via ffprobe
    import subprocess, json as _json
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(video_path)],
        capture_output=True,
        text=True,
    )
    source_width, source_height = 1280, 720  # fallback
    if probe.returncode == 0:
        streams = _json.loads(probe.stdout).get("streams", [])
        for s in streams:
            if s.get("codec_type") == "video":
                source_width = int(s.get("width", source_width))
                source_height = int(s.get("height", source_height))
                break

    crop_width = int(source_height * 9 / 16)

    from canal_soberania.utils.reframe import detect_face_crop_x
    crop_x = detect_face_crop_x(video_path, sample_time=clip.start_s + 2.0)
    if crop_x is None:
        crop_x = (source_width - crop_width) // 2

    return FaceCropResponse(
        crop_x=crop_x,
        crop_width=crop_width,
        source_width=source_width,
        source_height=source_height,
    )


@router.get("/{clip_id}/source-video")
def stream_source_video(
    clip_id: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> FileResponse:
    """Serve o arquivo de vídeo original (usado pelo player HTML5 no frontend)."""
    clip = service.get_clip(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")

    # Preferir o clipe editado vertical (se já processado)
    for candidate_path in [clip.clip_path_vertical, clip.clip_path_horizontal]:
        if candidate_path:
            p = Path(candidate_path)
            if p.exists():
                return FileResponse(
                    path=p,
                    media_type="video/mp4",
                    filename=p.name,
                    headers={"Accept-Ranges": "bytes"},
                )

    # Fallback: vídeo-fonte original
    video = service.get_video(clip.video_id)
    if video and video.video_path:
        p = Path(video.video_path)
        if p.exists():
            return FileResponse(
                path=p,
                media_type="video/mp4",
                filename=p.name,
                headers={"Accept-Ranges": "bytes"},
            )

    raise HTTPException(status_code=404, detail="Arquivo de vídeo não disponível")
