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


# ---------------------------------------------------------------------------
# GET /clips/{id}/face-crop
# ---------------------------------------------------------------------------


def test_face_crop_clip_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_clip.return_value = None
    r = client.get("/clips/notfound_0_60/face-crop", headers=auth_headers)
    assert r.status_code == 404


def test_face_crop_video_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_video.return_value = None
    r = client.get(f"/clips/{_CLIP_ID}/face-crop", headers=auth_headers)
    assert r.status_code == 404


def test_face_crop_video_no_path(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    from canal_soberania.models import Video, VideoStatus

    mock_service.get_video.return_value = Video(
        video_id=_VIDEO_ID,
        canal_id="ch",
        title="T",
        published_at="2024-01-01T00:00:00Z",
        status=VideoStatus.TRANSCRIBED,
        video_path=None,
    )
    r = client.get(f"/clips/{_CLIP_ID}/face-crop", headers=auth_headers)
    assert r.status_code == 404


def test_face_crop_file_missing(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    from canal_soberania.models import Video, VideoStatus

    mock_service.get_video.return_value = Video(
        video_id=_VIDEO_ID,
        canal_id="ch",
        title="T",
        published_at="2024-01-01T00:00:00Z",
        status=VideoStatus.TRANSCRIBED,
        video_path="/nonexistent/path/video.mp4",
    )
    r = client.get(f"/clips/{_CLIP_ID}/face-crop", headers=auth_headers)
    assert r.status_code == 404


def test_face_crop_happy_path(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: "Path",  # type: ignore[name-defined]
) -> None:
    from pathlib import Path

    from canal_soberania.models import Video, VideoStatus

    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"fake")

    mock_service.get_video.return_value = Video(
        video_id=_VIDEO_ID,
        canal_id="ch",
        title="T",
        published_at="2024-01-01T00:00:00Z",
        status=VideoStatus.TRANSCRIBED,
        video_path=str(video_file),
    )

    import subprocess
    import json as _json

    fake_probe = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=_json.dumps({"streams": [{"codec_type": "video", "width": 1920, "height": 1080}]}),
        stderr="",
    )

    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_probe)
    monkeypatch.setattr(
        "canal_soberania.utils.reframe.detect_face_crop_x",
        lambda *a, **kw: 100,
    )

    r = client.get(f"/clips/{_CLIP_ID}/face-crop", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["source_width"] == 1920
    assert body["source_height"] == 1080
    assert body["crop_x"] == 100


def test_face_crop_ffprobe_fails_fallback(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: "Path",  # type: ignore[name-defined]
) -> None:
    from pathlib import Path

    from canal_soberania.models import Video, VideoStatus

    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"fake")

    mock_service.get_video.return_value = Video(
        video_id=_VIDEO_ID,
        canal_id="ch",
        title="T",
        published_at="2024-01-01T00:00:00Z",
        status=VideoStatus.TRANSCRIBED,
        video_path=str(video_file),
    )

    import subprocess

    fake_probe = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="error")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_probe)
    monkeypatch.setattr(
        "canal_soberania.utils.reframe.detect_face_crop_x",
        lambda *a, **kw: None,
    )

    r = client.get(f"/clips/{_CLIP_ID}/face-crop", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["source_width"] == 1280  # fallback
    assert body["source_height"] == 720  # fallback
    crop_width = int(720 * 9 / 16)
    assert body["crop_x"] == (1280 - crop_width) // 2  # centrado


# ---------------------------------------------------------------------------
# GET /clips/{id}/source-video
# ---------------------------------------------------------------------------


def test_source_video_clip_not_found(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    mock_service.get_clip.return_value = None
    r = client.get("/clips/notfound_0_60/source-video", headers=auth_headers)
    assert r.status_code == 404


def test_source_video_prefers_vertical(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_service: MagicMock,
    tmp_path: "Path",  # type: ignore[name-defined]
) -> None:
    from pathlib import Path

    vert = tmp_path / "clip_vertical.mp4"
    vert.write_bytes(b"fake")

    clip = Clip(
        clip_id=_CLIP_ID,
        video_id=_VIDEO_ID,
        start_s=10.0,
        end_s=70.0,
        clip_path_vertical=str(vert),
        clip_path_horizontal=None,
    )
    mock_service.get_clip.return_value = clip

    r = client.get(f"/clips/{_CLIP_ID}/source-video", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("video/mp4")


def test_source_video_fallback_horizontal(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_service: MagicMock,
    tmp_path: "Path",  # type: ignore[name-defined]
) -> None:
    from pathlib import Path

    horiz = tmp_path / "clip_horiz.mp4"
    horiz.write_bytes(b"fake")

    clip = Clip(
        clip_id=_CLIP_ID,
        video_id=_VIDEO_ID,
        start_s=10.0,
        end_s=70.0,
        clip_path_vertical=None,
        clip_path_horizontal=str(horiz),
    )
    mock_service.get_clip.return_value = clip

    r = client.get(f"/clips/{_CLIP_ID}/source-video", headers=auth_headers)
    assert r.status_code == 200


def test_source_video_fallback_source(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_service: MagicMock,
    tmp_path: "Path",  # type: ignore[name-defined]
) -> None:
    from pathlib import Path

    from canal_soberania.models import Video, VideoStatus

    src = tmp_path / "source.mp4"
    src.write_bytes(b"fake")

    clip = Clip(
        clip_id=_CLIP_ID,
        video_id=_VIDEO_ID,
        start_s=10.0,
        end_s=70.0,
        clip_path_vertical=None,
        clip_path_horizontal=None,
    )
    mock_service.get_clip.return_value = clip
    mock_service.get_video.return_value = Video(
        video_id=_VIDEO_ID,
        canal_id="ch",
        title="T",
        published_at="2024-01-01T00:00:00Z",
        status=VideoStatus.TRANSCRIBED,
        video_path=str(src),
    )

    r = client.get(f"/clips/{_CLIP_ID}/source-video", headers=auth_headers)
    assert r.status_code == 200


def test_source_video_all_missing(
    client: TestClient, auth_headers: dict[str, str], mock_service: MagicMock
) -> None:
    from canal_soberania.models import Video, VideoStatus

    clip = Clip(
        clip_id=_CLIP_ID,
        video_id=_VIDEO_ID,
        start_s=10.0,
        end_s=70.0,
        clip_path_vertical=None,
        clip_path_horizontal=None,
    )
    mock_service.get_clip.return_value = clip
    mock_service.get_video.return_value = Video(
        video_id=_VIDEO_ID,
        canal_id="ch",
        title="T",
        published_at="2024-01-01T00:00:00Z",
        status=VideoStatus.TRANSCRIBED,
        video_path="/nonexistent/video.mp4",
    )

    r = client.get(f"/clips/{_CLIP_ID}/source-video", headers=auth_headers)
    assert r.status_code == 404
