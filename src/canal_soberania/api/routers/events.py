"""Router: /events — Server-Sent Events."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from canal_soberania.api.auth import verify_token
from canal_soberania.api.deps import get_sse_bridge
from canal_soberania.api.sse import SSEBridge

router = APIRouter(tags=["events"])


@router.get("/events")
async def stream_events(
    request: Request,
    bridge: SSEBridge = Depends(get_sse_bridge),
    _: None = Depends(verify_token),
) -> StreamingResponse:
    """Conecta ao stream de eventos do pipeline (Server-Sent Events)."""

    async def generator() -> AsyncGenerator[str, None]:
        async for data in bridge.stream():
            if await request.is_disconnected():
                break
            yield data

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
