"""FastAPI dependencies reutilizáveis."""

from __future__ import annotations

from fastapi import Request

from canal_soberania.api.sse import SSEBridge
from canal_soberania.services.pipeline_service import PipelineService


def get_service(request: Request) -> PipelineService:
    service: PipelineService = request.app.state.service
    return service


def get_sse_bridge(request: Request) -> SSEBridge:
    return request.app.state.sse_bridge  # type: ignore[no-any-return]
