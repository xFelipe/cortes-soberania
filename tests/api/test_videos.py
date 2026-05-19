"""Testes para GET/POST /videos."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from canal_soberania.models import VideoStatus

_VIDEO_ID = "dQw4w9WgXcQ"


def test_list_videos(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.get("/videos", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["video_id"] == _VIDEO_ID


def test_list_videos_no_auth(client: TestClient) -> None:
    r = client.get("/videos")
    assert r.status_code == 401


def test_list_videos_wrong_token(client: TestClient) -> None:
    r = client.get("/videos", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401


def test_list_videos_status_filter(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.get("/videos?status=discovered", headers=auth_headers)
    assert r.status_code == 200
    mock_service.get_videos.assert_called_once_with(status=VideoStatus.DISCOVERED)


def test_list_videos_limit(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/videos?limit=1", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) <= 1


def test_get_video(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.get(f"/videos/{_VIDEO_ID}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["video_id"] == _VIDEO_ID


def test_get_video_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_video.return_value = None
    r = client.get("/videos/zzzzzzzzzzz", headers=auth_headers)
    assert r.status_code == 404


def test_approve_video(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.post(f"/videos/{_VIDEO_ID}/approve", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["video_id"] == _VIDEO_ID
    mock_service.approve_video.assert_called_once_with(_VIDEO_ID)


def test_approve_video_service_error(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.approve_video.side_effect = ValueError("Estado inválido")
    r = client.post(f"/videos/{_VIDEO_ID}/approve", headers=auth_headers)
    assert r.status_code == 400


def test_reject_video(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.post(f"/videos/{_VIDEO_ID}/reject", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["video_id"] == _VIDEO_ID
    mock_service.reject_video.assert_called_once_with(_VIDEO_ID)


def test_reject_video_service_error(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.reject_video.side_effect = ValueError("Estado inválido")
    r = client.post(f"/videos/{_VIDEO_ID}/reject", headers=auth_headers)
    assert r.status_code == 400
