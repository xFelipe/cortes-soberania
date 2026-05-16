"""Testes para stages/thumbnail.py (ffmpeg e Pillow mockados)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from canal_soberania.db import connect, init_db, insert_clip, insert_video
from canal_soberania.models import Clip, Video
from canal_soberania.stages.thumbnail import (
    _wrap_text,
    extract_frame,
    generate_thumbnail,
    make_thumbnail_for_clip,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def clip() -> Clip:
    return Clip(
        clip_id="abc123XYZ01_30_90",
        video_id="abc123XYZ01",
        start_s=30.0,
        end_s=90.0,
        hook="Brasil perde soberania na indústria",
        payoff="política industrial necessária",
        tema_soberania="industria_defesa",
        score_viral=8,
        score_relevancia=9,
    )


@pytest.fixture
def clip_in_db(db: sqlite3.Connection, clip: Clip) -> Clip:
    video = Video(
        video_id="abc123XYZ01",
        canal_id="canal_test",
        title="Podcast soberania",
        published_at="2026-01-01T00:00:00Z",
    )
    insert_video(db, video)
    insert_clip(db, clip)
    return clip


# ---------------------------------------------------------------------------
# _wrap_text
# ---------------------------------------------------------------------------


def test_wrap_text_single_line() -> None:
    from PIL import ImageFont

    font = ImageFont.load_default()
    lines = _wrap_text("hello world", font, max_width=10000)
    assert lines == ["hello world"]


def test_wrap_text_breaks_long_text() -> None:
    from PIL import ImageFont

    font = ImageFont.load_default()
    # max_width muito pequeno força quebra
    lines = _wrap_text("um dois tres quatro cinco", font, max_width=1)
    assert len(lines) == 5


def test_wrap_text_empty() -> None:
    from PIL import ImageFont

    font = ImageFont.load_default()
    assert _wrap_text("", font, max_width=500) == []


# ---------------------------------------------------------------------------
# extract_frame
# ---------------------------------------------------------------------------


def test_extract_frame_success(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    out = tmp_path / "frame.jpg"

    def fake_run(args: list[str], **kwargs: object) -> MagicMock:
        out.write_bytes(b"fake_jpeg")
        return MagicMock(returncode=0)

    with patch("canal_soberania.stages.thumbnail.subprocess.run", side_effect=fake_run):
        result = extract_frame(video, seek_s=2.0, output_path=out)

    assert result is True
    assert out.exists()


def test_extract_frame_ffmpeg_failure(tmp_path: Path) -> None:
    import subprocess

    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    out = tmp_path / "frame.jpg"

    with patch(
        "canal_soberania.stages.thumbnail.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "ffmpeg"),
    ):
        result = extract_frame(video, seek_s=2.0, output_path=out)

    assert result is False


def test_extract_frame_ffmpeg_not_found(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    out = tmp_path / "frame.jpg"

    with patch(
        "canal_soberania.stages.thumbnail.subprocess.run",
        side_effect=FileNotFoundError("ffmpeg not found"),
    ):
        result = extract_frame(video, seek_s=2.0, output_path=out)

    assert result is False


# ---------------------------------------------------------------------------
# generate_thumbnail
# ---------------------------------------------------------------------------


def test_generate_thumbnail_creates_jpeg(tmp_path: Path) -> None:
    out = tmp_path / "thumb.jpg"
    result = generate_thumbnail(
        frame_path=None,
        hook_text="BRASIL PERDE SOBERANIA",
        output_path=out,
    )
    assert result == out
    assert out.exists()
    img = Image.open(out)
    assert img.format == "JPEG"
    assert img.size == (1280, 720)


def test_generate_thumbnail_with_frame(tmp_path: Path) -> None:
    frame = tmp_path / "frame.jpg"
    img_src = Image.new("RGB", (1920, 1080), (100, 150, 200))
    img_src.save(str(frame), "JPEG")

    out = tmp_path / "thumb.jpg"
    generate_thumbnail(frame_path=frame, hook_text="SOBERANIA", output_path=out)

    assert out.exists()
    img = Image.open(out)
    assert img.size == (1280, 720)


def test_generate_thumbnail_with_logo(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    logo_img = Image.new("RGBA", (200, 80), (255, 0, 0, 200))
    logo_img.save(str(logo), "PNG")

    out = tmp_path / "thumb.jpg"
    generate_thumbnail(frame_path=None, hook_text="HOOK", output_path=out, logo_path=logo)

    assert out.exists()


def test_generate_thumbnail_missing_logo_is_ok(tmp_path: Path) -> None:
    out = tmp_path / "thumb.jpg"
    missing_logo = tmp_path / "nonexistent_logo.png"
    generate_thumbnail(frame_path=None, hook_text="HOOK", output_path=out, logo_path=missing_logo)
    assert out.exists()


def test_generate_thumbnail_creates_parent_dirs(tmp_path: Path) -> None:
    out = tmp_path / "subdir" / "nested" / "thumb.jpg"
    generate_thumbnail(frame_path=None, hook_text="TEST", output_path=out)
    assert out.exists()


# ---------------------------------------------------------------------------
# make_thumbnail_for_clip
# ---------------------------------------------------------------------------


def test_make_thumbnail_dry_run(
    clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path
) -> None:
    thumbs_dir = tmp_path / "thumbs"
    result = make_thumbnail_for_clip(
        clip=clip_in_db,
        conn=db,
        thumbs_dir=thumbs_dir,
        dry_run=True,
    )
    assert result is None
    assert not thumbs_dir.exists() or not (thumbs_dir / f"{clip_in_db.clip_id}.jpg").exists()


def test_make_thumbnail_returns_existing(
    clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path
) -> None:
    thumbs_dir = tmp_path / "thumbs"
    thumbs_dir.mkdir()
    existing = thumbs_dir / f"{clip_in_db.clip_id}.jpg"
    Image.new("RGB", (1280, 720)).save(str(existing), "JPEG")

    result = make_thumbnail_for_clip(
        clip=clip_in_db,
        conn=db,
        thumbs_dir=thumbs_dir,
        dry_run=False,
    )
    assert result == existing

    row = db.execute(
        "SELECT status FROM clips WHERE clip_id = ?", (clip_in_db.clip_id,)
    ).fetchone()
    assert row["status"] == "thumbnail_ready"


def test_make_thumbnail_fallback_no_video(
    clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path
) -> None:
    thumbs_dir = tmp_path / "thumbs"
    result = make_thumbnail_for_clip(
        clip=clip_in_db,
        conn=db,
        thumbs_dir=thumbs_dir,
        dry_run=False,
    )
    assert result is not None
    assert result.exists()
    row = db.execute(
        "SELECT status, thumb_path FROM clips WHERE clip_id = ?", (clip_in_db.clip_id,)
    ).fetchone()
    assert row["status"] == "thumbnail_ready"
    assert row["thumb_path"] is not None


def test_make_thumbnail_with_vertical_video(
    clip_in_db: Clip, db: sqlite3.Connection, tmp_path: Path
) -> None:
    vertical = tmp_path / "clips" / f"{clip_in_db.clip_id}_vertical.mp4"
    vertical.parent.mkdir(parents=True)
    vertical.write_bytes(b"fake_video")

    db.execute(
        "UPDATE clips SET clip_path_vertical = ? WHERE clip_id = ?",
        (str(vertical), clip_in_db.clip_id),
    )
    db.commit()

    thumbs_dir = tmp_path / "thumbs"

    def fake_extract(video_path: object, seek_s: object, output_path: object) -> bool:
        from pathlib import Path as P
        P(str(output_path)).write_bytes(b"fake_frame")
        Image.new("RGB", (1080, 1920)).save(str(output_path), "JPEG")
        return True

    with patch("canal_soberania.stages.thumbnail.extract_frame", side_effect=fake_extract):
        result = make_thumbnail_for_clip(
            clip=clip_in_db,
            conn=db,
            thumbs_dir=thumbs_dir,
        )

    assert result is not None
    assert result.exists()
