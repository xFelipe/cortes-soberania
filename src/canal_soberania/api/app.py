"""Factory da aplicação FastAPI."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from canal_soberania.api.routers import canais, clips, config, events, inbox, stages, stats, videos
from canal_soberania.api.sse import SSEBridge
from canal_soberania.config import CanaisConfig
from canal_soberania.services.pipeline_service import PipelineService


def create_app(
    service: PipelineService,
    conn: sqlite3.Connection,
    paths: dict[str, Path],
    token: str,
    canais_cfg: CanaisConfig | None = None,
) -> FastAPI:
    """Cria e configura a aplicação FastAPI."""
    app = FastAPI(
        title="Canal Soberania API",
        version="2.0.0",
        description="API REST para o pipeline Canal Soberania. Auth: Bearer token.",
        docs_url="/docs",
        redoc_url=None,
    )

    # CORS para Tauri (localhost) e acesso LAN opcional
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["tauri://localhost", "http://localhost", "http://127.0.0.1"],
        allow_origin_regex=r"http://localhost:\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Estado global (acessível via request.app.state)
    app.state.service = service
    app.state.conn = conn
    app.state.api_token = token
    app.state.paths = paths
    app.state.sse_bridge = SSEBridge(service.event_bus)

    if canais_cfg is None:
        from canal_soberania.config import load_canais
        canais_path = paths.get("canais_path")
        if canais_path and canais_path.exists():
            canais_cfg = load_canais(canais_path)
    app.state.canais_cfg = canais_cfg

    # Routers
    app.include_router(videos.router)
    app.include_router(clips.router)
    app.include_router(canais.router)
    app.include_router(stages.router)
    app.include_router(stats.router)
    app.include_router(inbox.router)
    app.include_router(events.router)
    app.include_router(config.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
