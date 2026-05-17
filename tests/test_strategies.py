"""Testes para os Strategy protocols e implementações concretas."""

from __future__ import annotations

from pathlib import Path

import pytest

from canal_soberania.core.strategies import CropParams, ReframeStrategy, TranscriptionBackend, UploadAdapter
from canal_soberania.strategies.reframe import CenterCropReframe, FaceDetectionReframe
from canal_soberania.strategies.upload import ManualQueueAdapter, YouTubeUploadAdapter


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


def test_center_crop_satisfies_reframe_protocol() -> None:
    assert isinstance(CenterCropReframe(), ReframeStrategy)


def test_face_detection_satisfies_reframe_protocol() -> None:
    assert isinstance(FaceDetectionReframe(), ReframeStrategy)


def test_manual_queue_satisfies_upload_protocol() -> None:
    assert isinstance(ManualQueueAdapter(Path("/tmp")), UploadAdapter)


def test_youtube_adapter_satisfies_upload_protocol() -> None:
    assert isinstance(YouTubeUploadAdapter(), UploadAdapter)


# ---------------------------------------------------------------------------
# CenterCropReframe
# ---------------------------------------------------------------------------


def test_center_crop_name() -> None:
    assert CenterCropReframe().name == "center_crop"


def test_center_crop_16x9_to_9x16() -> None:
    strategy = CenterCropReframe()
    params = strategy.get_crop_params(
        frame=None,
        source_width=1920,
        source_height=1080,
        target_width=1080,
        target_height=1920,
    )
    assert isinstance(params, CropParams)
    # crop_w = 1080 * 1080/1920 = 607
    assert params.width == 607
    assert params.height == 1080
    assert params.y == 0
    # centralizado: x = (1920 - 607) // 2 = 656
    assert params.x == 656


def test_center_crop_already_portrait() -> None:
    strategy = CenterCropReframe()
    params = strategy.get_crop_params(
        frame=None,
        source_width=1080,
        source_height=1920,
        target_width=1080,
        target_height=1920,
    )
    assert params.x == 0
    assert params.width == 1080


# ---------------------------------------------------------------------------
# FaceDetectionReframe (sem mediapipe: fallback para center)
# ---------------------------------------------------------------------------


def test_face_detection_name() -> None:
    assert FaceDetectionReframe().name == "face_detection"


def test_face_detection_fallback_to_center_when_no_mediapipe() -> None:
    strategy = FaceDetectionReframe()
    # Sem frame real / sem mediapipe → comportamento idêntico ao center crop
    params = strategy.get_crop_params(
        frame=None,
        source_width=1920,
        source_height=1080,
    )
    center = CenterCropReframe().get_crop_params(
        frame=None,
        source_width=1920,
        source_height=1080,
    )
    assert params == center


# ---------------------------------------------------------------------------
# ManualQueueAdapter
# ---------------------------------------------------------------------------


def test_manual_queue_platform() -> None:
    adapter = ManualQueueAdapter(Path("/tmp"))
    assert adapter.platform == "manual_queue"


def test_manual_queue_copies_file(tmp_path: Path) -> None:
    queue_dir = tmp_path / "queue"
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake_video_data")

    adapter = ManualQueueAdapter(queue_dir)
    result_id = adapter.upload(
        video_path=video,
        title="Título",
        description="Desc",
        tags=["tag1", "tag2"],
    )
    assert (queue_dir / "clip.mp4").exists()
    assert result_id == "clip"


def test_manual_queue_writes_metadata(tmp_path: Path) -> None:
    queue_dir = tmp_path / "queue"
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"data")

    ManualQueueAdapter(queue_dir).upload(
        video_path=video,
        title="Meu Título",
        description="Minha Desc",
        tags=["a", "b"],
    )
    meta = (queue_dir / "clip.txt").read_text()
    assert "Meu Título" in meta
    assert "a, b" in meta


# ---------------------------------------------------------------------------
# YouTubeUploadAdapter
# ---------------------------------------------------------------------------


def test_youtube_adapter_platform() -> None:
    assert YouTubeUploadAdapter().platform == "youtube"


def test_youtube_adapter_upload_raises_not_implemented(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"data")
    with pytest.raises(NotImplementedError):
        YouTubeUploadAdapter().upload(
            video_path=video,
            title="T",
            description="D",
            tags=[],
        )
