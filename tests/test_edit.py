"""Testes para stages/edit.py e utils/ffmpeg.py (subprocess mockado)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.db import connect, init_db
from canal_soberania.models import Clip
from canal_soberania.stages.edit import (
    _ts_to_ass,
    _words_from_segment,
    detect_face_crop_x,
    edit_clip,
    generate_ass,
)
from canal_soberania.utils.ffmpeg import FFmpegError, _run, concat_videos, cut_video

SCHEMA = Path(__file__).parent.parent / "schema.sql"

_SAMPLE_SEGMENTS = [
    {"start": 30.0, "end": 50.0, "text": "O Brasil perde soberania industrial."},
    {"start": 50.0, "end": 70.0, "text": "O pré-sal é um ativo estratégico."},
    {"start": 70.0, "end": 90.0, "text": "Precisamos de política industrial."},
]


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def source_video(tmp_path: Path) -> Path:
    p = tmp_path / "video" / "dQw4w9WgXcQ.mp4"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"fake_video_data")
    return p


@pytest.fixture
def transcript_file(tmp_path: Path) -> Path:
    p = tmp_path / "transcripts" / "dQw4w9WgXcQ.json"
    p.parent.mkdir()
    p.write_text(
        json.dumps({"video_id": "dQw4w9WgXcQ", "language": "pt", "segments": _SAMPLE_SEGMENTS}),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def clip() -> Clip:
    return Clip(
        clip_id="dQw4w9WgXcQ_30_90",
        video_id="dQw4w9WgXcQ",
        start_s=30.0,
        end_s=90.0,
        hook="O Brasil perde soberania",
        payoff="política industrial",
        tema_soberania="industria_defesa",
        score_viral=8,
        score_relevancia=9,
    )


# ---------------------------------------------------------------------------
# ASS generation helpers
# ---------------------------------------------------------------------------


def test_ts_to_ass_zero() -> None:
    assert _ts_to_ass(0.0) == "0:00:00.00"


def test_ts_to_ass_one_minute() -> None:
    assert _ts_to_ass(61.5) == "0:01:01.50"


def test_words_from_segment_distributes_evenly() -> None:
    words = _words_from_segment("hello world test", 0.0, 3.0)
    assert len(words) == 3
    assert words[0] == (0.0, 1.0, "hello")
    assert words[1] == (1.0, 2.0, "world")
    assert words[2] == (2.0, 3.0, "test")


def test_words_from_segment_empty() -> None:
    assert _words_from_segment("", 0.0, 5.0) == []


def test_generate_ass_creates_valid_file(tmp_path: Path) -> None:
    ass_path = tmp_path / "subs.ass"
    generate_ass(_SAMPLE_SEGMENTS, clip_start_s=30.0, output_path=ass_path)
    content = ass_path.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "Style: Caption" in content
    assert "Dialogue:" in content
    # Verifica que o texto está em maiúsculas
    assert "BRASIL" in content or "PRÉ-SAL" in content or "SOBERANIA" in content


def test_generate_ass_offsets_by_clip_start(tmp_path: Path) -> None:
    ass_path = tmp_path / "subs.ass"
    # clip começa em 30s, então primeiro segmento começa em 0s relativo
    generate_ass(_SAMPLE_SEGMENTS, clip_start_s=30.0, output_path=ass_path)
    content = ass_path.read_text(encoding="utf-8")
    # Primeiro diálogo deve começar em 0:00:00.xx (offset = 30 - 30 = 0)
    assert "0:00:00." in content


# ---------------------------------------------------------------------------
# utils/ffmpeg.py
# ---------------------------------------------------------------------------


def test_run_raises_on_nonzero(tmp_path: Path) -> None:
    with pytest.raises(FFmpegError):
        _run(["false"])  # comando que sempre falha com exit 1


def test_cut_video_calls_ffmpeg(tmp_path: Path) -> None:
    inp = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    inp.write_bytes(b"x")

    with patch("canal_soberania.utils.ffmpeg.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        cut_video(inp, out, start_s=10.0, end_s=70.0)

    called_args = mock_run.call_args[0][0]
    assert "ffmpeg" in called_args
    assert "-ss" in called_args
    assert "-t" in called_args
    assert "60.0" in called_args  # duration = end_s - start_s


def test_concat_videos_single_input(tmp_path: Path) -> None:
    src = tmp_path / "src.mp4"
    dst = tmp_path / "dst.mp4"
    src.write_bytes(b"content")
    concat_videos([src], dst)
    assert dst.read_bytes() == b"content"


def test_concat_videos_raises_on_empty() -> None:
    with pytest.raises(FFmpegError):
        concat_videos([], Path("/tmp/out.mp4"))


# ---------------------------------------------------------------------------
# detect_face_crop_x
# ---------------------------------------------------------------------------


def test_detect_face_crop_x_returns_none_without_mediapipe(tmp_path: Path) -> None:
    p = tmp_path / "vid.mp4"
    p.write_bytes(b"x")
    with patch("canal_soberania.stages.edit.detect_face_crop_x", return_value=None):
        result = detect_face_crop_x(p)
    assert result is None


# ---------------------------------------------------------------------------
# edit_clip integration (all ffmpeg calls mocked)
# ---------------------------------------------------------------------------


def _mock_ffmpeg_calls(tmp_path: Path, clip_id: str) -> None:
    """Patches all ffmpeg functions to succeed and create output files."""
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    def fake_cut(*args: object, **kwargs: object) -> None:
        Path(str(args[1])).write_bytes(b"cut_video")

    def fake_crop(*args: object, **kwargs: object) -> None:
        Path(str(args[1])).write_bytes(b"cropped")

    def fake_add_subs(*args: object, **kwargs: object) -> None:
        Path(str(args[1])).write_bytes(b"with_subs")

    def fake_concat(*args: object, **kwargs: object) -> None:
        Path(str(args[1])).write_bytes(b"concat")

    def fake_encode(*args: object, **kwargs: object) -> None:
        Path(str(args[1])).write_bytes(b"encoded")

    def fake_dims(*args: object, **kwargs: object) -> tuple[int, int]:
        return 1920, 1080

    return {
        "cut_video": fake_cut,
        "crop_and_scale": fake_crop,
        "add_subtitles": fake_add_subs,
        "concat_videos": fake_concat,
        "encode_final": fake_encode,
        "get_video_dimensions": fake_dims,
        "detect_face_crop_x": lambda p: None,
    }


def test_edit_clip_success(
    clip: Clip, source_video: Path, transcript_file: Path, tmp_path: Path
) -> None:
    clips_dir = tmp_path / "clips"
    patches = _mock_ffmpeg_calls(tmp_path, clip.clip_id)

    with patch.multiple("canal_soberania.stages.edit", **patches):
        vertical, horizontal = edit_clip(
            clip=clip,
            source_video_path=source_video,
            transcript_path=transcript_file,
            clips_dir=clips_dir,
        )

    # Arquivos foram criados pelos fakes
    assert vertical is not None
    assert horizontal is not None


def test_edit_clip_dry_run(
    clip: Clip, source_video: Path, transcript_file: Path, tmp_path: Path
) -> None:
    clips_dir = tmp_path / "clips"
    with patch("canal_soberania.stages.edit.cut_video") as mock_cut:
        vertical, horizontal = edit_clip(
            clip=clip,
            source_video_path=source_video,
            transcript_path=transcript_file,
            clips_dir=clips_dir,
            dry_run=True,
        )
        mock_cut.assert_not_called()

    assert vertical is None
    assert horizontal is None


def test_edit_clip_cut_failure_returns_none(
    clip: Clip, source_video: Path, transcript_file: Path, tmp_path: Path
) -> None:
    clips_dir = tmp_path / "clips"
    patches = _mock_ffmpeg_calls(tmp_path, clip.clip_id)
    patches["cut_video"] = MagicMock(side_effect=FFmpegError("cut failed"))

    with patch.multiple("canal_soberania.stages.edit", **patches):
        vertical, horizontal = edit_clip(
            clip=clip,
            source_video_path=source_video,
            transcript_path=transcript_file,
            clips_dir=clips_dir,
        )

    assert vertical is None
    assert horizontal is None
