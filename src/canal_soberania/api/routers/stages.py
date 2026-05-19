"""Router: /stages e /pipeline"""

from __future__ import annotations

import threading
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException

from canal_soberania.api.auth import verify_token
from canal_soberania.api.deps import get_service
from canal_soberania.services.pipeline_service import PipelineService

router = APIRouter(tags=["pipeline"])

_STAGE_MAP: dict[str, Callable[[PipelineService], None]] = {
    "discover":          lambda s: s.run_discover(),
    "triage_metadata":   lambda s: s.run_triage_metadata(),
    "triage_caption":    lambda s: s.run_triage_caption(),
    "download":          lambda s: s.run_download(),
    "transcribe":        lambda s: s.run_transcribe(),
    "triage_transcript": lambda s: s.run_triage_transcript(),
    "find_clips":        lambda s: s.run_find_clips(),
    "edit":              lambda s: s.run_edit(),
    "thumbnail":         lambda s: s.run_thumbnail(),
    "generate_metadata": lambda s: s.run_generate_metadata(),
    "upload_youtube":    lambda s: s.run_upload_youtube(),
    "upload_tiktok":     lambda s: s.run_upload_tiktok(),
    "sync_youtube":      lambda s: s.run_sync_youtube(),
    "auto":              lambda s: s.run_pipeline_auto(),
}


@router.post("/stages/{name}/run")
def run_stage(
    name: str,
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    """Executa um stage do pipeline em background thread."""
    fn = _STAGE_MAP.get(name)
    if fn is None:
        raise HTTPException(
            status_code=404,
            detail=f"Stage não encontrado: {name}. Disponíveis: {sorted(_STAGE_MAP)}",
        )
    service.reset_cancel()
    thread = threading.Thread(target=fn, args=(service,), daemon=True, name=f"stage-{name}")
    thread.start()
    return {"status": "started", "stage": name}


@router.post("/pipeline/cancel")
def cancel_pipeline(
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, str]:
    service.cancel()
    return {"status": "cancelling"}


@router.post("/pipeline/reset")
def reset_stuck(
    service: PipelineService = Depends(get_service),
    _: None = Depends(verify_token),
) -> dict[str, int]:
    videos = service.reset_stuck_videos()
    clips = service.reset_stuck_clips()
    return {"reset_videos": videos, "reset_clips": clips}
