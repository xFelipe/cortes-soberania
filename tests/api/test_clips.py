"""Testes para GET/POST/PATCH/DELETE /clips."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from canal_soberania.models import Clip, ClipStatus

_CLIP_ID = "dQw4w9WgXcQ_10_70"
_VIDEO_ID = "dQw4w9WgXcQ"


def test_list_clips(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.get("/clips", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["clip_id"] == _CLIP_ID


def test_list_clips_no_auth(client: TestClient) -> None:
    r = client.get("/clips")
    assert r.status_code == 401


def test_list_clips_filter_video_match(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get(f"/clips?video_id={_VIDEO_ID}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["video_id"] == _VIDEO_ID


def test_list_clips_filter_video_no_match(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.get("/clips?video_id=outrovideo123", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_get_clip(client: TestClient, auth_headers: dict[str, str]) -> None:
    r = client.get(f"/clips/{_CLIP_ID}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["clip_id"] == _CLIP_ID


def test_get_clip_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_clip.return_value = None
    r = client.get("/clips/notfound_0_60", headers=auth_headers)
    assert r.status_code == 404


def test_approve_clip(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.post(f"/clips/{_CLIP_ID}/approve", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "upload_started"
    assert body["clip_id"] == _CLIP_ID


def test_approve_clip_wrong_status(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    bad_clip = Clip(
        clip_id=_CLIP_ID,
        video_id=_VIDEO_ID,
        start_s=10.0,
        end_s=70.0,
        status=ClipStatus.PROCESSING_ERROR,
    )
    mock_service.get_clip.return_value = bad_clip
    r = client.post(f"/clips/{_CLIP_ID}/approve", headers=auth_headers)
    assert r.status_code == 400


def test_approve_clip_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_clip.return_value = None
    r = client.post(f"/clips/{_CLIP_ID}/approve", headers=auth_headers)
    assert r.status_code == 404


def test_reject_clip(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.post(f"/clips/{_CLIP_ID}/reject", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["clip_id"] == _CLIP_ID
    mock_service._clip_repo.update_status.assert_called_once_with(
        _CLIP_ID, ClipStatus.REJECTED_YOUTUBE
    )


def test_reject_clip_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_clip.return_value = None
    r = client.post(f"/clips/{_CLIP_ID}/reject", headers=auth_headers)
    assert r.status_code == 404


def test_trim_clip(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.post(
        f"/clips/{_CLIP_ID}/trim",
        headers=auth_headers,
        json={"start_s": 5.0, "end_s": 45.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "trimmed"
    assert body["start_s"] == pytest.approx(5.0)
    assert body["end_s"] == pytest.approx(45.0)
    mock_service._clip_repo.update_trim.assert_called_once_with(_CLIP_ID, 5.0, 45.0)


def test_trim_clip_end_before_start(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.post(
        f"/clips/{_CLIP_ID}/trim",
        headers=auth_headers,
        json={"start_s": 50.0, "end_s": 10.0},
    )
    assert r.status_code == 400


def test_trim_clip_equal_start_end(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    r = client.post(
        f"/clips/{_CLIP_ID}/trim",
        headers=auth_headers,
        json={"start_s": 10.0, "end_s": 10.0},
    )
    assert r.status_code == 400


def test_trim_clip_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_clip.return_value = None
    r = client.post(
        f"/clips/{_CLIP_ID}/trim",
        headers=auth_headers,
        json={"start_s": 5.0, "end_s": 45.0},
    )
    assert r.status_code == 404


def test_discard_clip(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    r = client.delete(f"/clips/{_CLIP_ID}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "discarded"
    assert body["clip_id"] == _CLIP_ID
    mock_service._clip_repo.delete.assert_called_once_with(_CLIP_ID)


def test_discard_clip_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_clip.return_value = None
    r = client.delete(f"/clips/{_CLIP_ID}", headers=auth_headers)
    assert r.status_code == 404


def test_patch_clip(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    payload = {
        "hook": "Novo hook",
        "title": "Novo título",
        "render_vertical": True,
        "render_horizontal": False,
    }
    r = client.patch(f"/clips/{_CLIP_ID}", headers=auth_headers, json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "updated"
    assert body["clip_id"] == _CLIP_ID
    mock_service.update_clip_text.assert_called_once()


def test_patch_clip_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_clip.return_value = None
    r = client.patch(
        f"/clips/{_CLIP_ID}",
        headers=auth_headers,
        json={"render_vertical": True, "render_horizontal": True},
    )
    assert r.status_code == 404
