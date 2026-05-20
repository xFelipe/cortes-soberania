"""Fixtures compartilhadas para testes da API."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from canal_soberania.api.app import create_app
from canal_soberania.config import CanaisConfig, Parametros
from canal_soberania.core.events import EventBus
from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus

_TOKEN = "test-token-abc123"


def _make_video(video_id: str = "dQw4w9WgXcQ", status: VideoStatus = VideoStatus.DISCOVERED) -> Video:
    return Video(
        video_id=video_id,
        canal_id="canal1",
        title="Título de teste",
        published_at="2024-01-15T10:00:00Z",
        status=status,
    )


def _make_clip(
    clip_id: str = "dQw4w9WgXcQ_10_70",
    status: ClipStatus = ClipStatus.METADATA_READY,
) -> Clip:
    return Clip(
        clip_id=clip_id,
        video_id="dQw4w9WgXcQ",
        start_s=10.0,
        end_s=70.0,
        hook="Abertura forte",
        title="Título do clipe",
        status=status,
    )


@pytest.fixture()
def mock_service() -> MagicMock:
    svc = MagicMock()
    svc.event_bus = EventBus()
    svc.get_videos.return_value = [_make_video()]
    svc.get_video.return_value = _make_video()
    svc.get_clips.return_value = [_make_clip()]
    svc.get_clip.return_value = _make_clip()
    svc.get_status_summary.return_value = {"discovered": 3, "metadata_ready": 1}
    svc.get_monthly_cost.return_value = 1.23
    # expose clip repo for direct access in routers
    svc._clip_repo = MagicMock()
    return svc


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS api_costs (
            date TEXT, provider TEXT, model TEXT,
            tokens_in INT, tokens_out INT, requests INT, cost_usd REAL,
            PRIMARY KEY (date, provider, model)
        );
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY, canal_id TEXT NOT NULL, title TEXT NOT NULL,
            published_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'discovered',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS clips (
            clip_id TEXT PRIMARY KEY, video_id TEXT NOT NULL,
            start_s REAL NOT NULL, end_s REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'identified',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    return c


@pytest.fixture()
def client(mock_service: MagicMock, conn: sqlite3.Connection) -> TestClient:
    canais_cfg = CanaisConfig(canais=[], parametros=Parametros())
    api = create_app(
        service=mock_service,
        conn=conn,
        paths={},
        token=_TOKEN,
        canais_cfg=canais_cfg,
    )
    return TestClient(api, raise_server_exceptions=True)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}"}
