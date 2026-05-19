"""Testes para models.py."""

import pytest
from pydantic import ValidationError

from canal_soberania.models import Clip, ClipStatus, Video, VideoStatus


def test_video_valid() -> None:
    v = Video(
        video_id="dQw4w9WgXcQ",
        canal_id="flow_podcast",
        title="Título do vídeo",
        published_at="2024-01-01T00:00:00Z",
    )
    assert v.status == VideoStatus.DISCOVERED
    assert v.tags == []


def test_video_invalid_id_too_short() -> None:
    with pytest.raises(ValidationError):
        Video(
            video_id="short",
            canal_id="x",
            title="T",
            published_at="2024-01-01T00:00:00Z",
        )


def test_video_invalid_id_too_long() -> None:
    with pytest.raises(ValidationError):
        Video(
            video_id="dQw4w9WgXcQX",  # 12 chars
            canal_id="x",
            title="T",
            published_at="2024-01-01T00:00:00Z",
        )


def test_clip_duracao() -> None:
    c = Clip(
        clip_id="dQw4w9WgXcQ_30_90",
        video_id="dQw4w9WgXcQ",
        start_s=30.0,
        end_s=90.0,
    )
    assert c.duracao_s == pytest.approx(60.0)


def test_clip_default_status() -> None:
    c = Clip(
        clip_id="dQw4w9WgXcQ_0_60",
        video_id="dQw4w9WgXcQ",
        start_s=0.0,
        end_s=60.0,
    )
    assert c.status == ClipStatus.IDENTIFIED
