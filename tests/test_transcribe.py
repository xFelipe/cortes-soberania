"""Testes para stages/transcribe.py (faster-whisper mockado)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.db import connect, get_videos_by_status, init_db, insert_video, update_video_paths
from canal_soberania.models import Video
from canal_soberania.stages.transcribe import (
    _format_ts,
    format_segments_for_prompt,
    save_transcript,
    transcribe_video,
)

SCHEMA = Path(__file__).parent.parent / "schema.sql"

_SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 4.5, "text": "O Brasil precisa de soberania."},
    {"start": 4.5, "end": 10.0, "text": "O pré-sal é estratégico."},
    {"start": 10.0, "end": 18.3, "text": "A política industrial define o futuro."},
]


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path, SCHEMA)
    return connect(db_path)


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    audio = tmp_path / "audio" / "dQw4w9WgXcQ.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"fake_audio_data")
    return audio


@pytest.fixture
def video(audio_file: Path) -> Video:
    return Video(
        video_id="dQw4w9WgXcQ",
        canal_id="flow_podcast",
        title="Soberania industrial",
        published_at="2026-05-10T12:00:00Z",
        status="downloaded",
        audio_path=str(audio_file),
    )


def _mock_whisper(segments: list[dict] | None = None) -> MagicMock:
    """Retorna um mock de WhisperModel."""
    if segments is None:
        segments = _SAMPLE_SEGMENTS

    mock_model = MagicMock()
    mock_info = MagicMock()
    mock_info.language = "pt"
    mock_info.language_probability = 0.99

    # Cria objetos de segmento que imitam os de faster-whisper
    seg_objects = []
    for s in segments:
        seg = MagicMock()
        seg.start = s["start"]
        seg.end = s["end"]
        seg.text = f"  {s['text']}  "  # Whisper retorna com espaços
        seg_objects.append(seg)

    mock_model.transcribe.return_value = (iter(seg_objects), mock_info)
    return mock_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_format_ts_zero() -> None:
    assert _format_ts(0.0) == "00:00:00.00"


def test_format_ts_one_hour() -> None:
    assert _format_ts(3661.5) == "01:01:01.50"


def test_format_segments_for_prompt() -> None:
    result = format_segments_for_prompt(_SAMPLE_SEGMENTS)
    assert "soberania" in result
    assert "[00:00:00.00" in result
    assert "pré-sal" in result


def test_format_segments_truncates() -> None:
    many_segments = [
        {"start": float(i), "end": float(i + 1), "text": "x" * 200}
        for i in range(200)
    ]
    result = format_segments_for_prompt(many_segments, max_chars=500)
    assert len(result) <= 500


# ---------------------------------------------------------------------------
# save_transcript
# ---------------------------------------------------------------------------


def test_save_transcript_writes_valid_json(tmp_path: Path) -> None:
    transcripts_dir = tmp_path / "transcripts"
    path = save_transcript("dQw4w9WgXcQ", _SAMPLE_SEGMENTS, transcripts_dir)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["video_id"] == "dQw4w9WgXcQ"
    assert data["language"] == "pt"
    assert len(data["segments"]) == 3
    assert data["segments"][0]["text"] == "O Brasil precisa de soberania."


def test_save_transcript_creates_dir(tmp_path: Path) -> None:
    transcripts_dir = tmp_path / "nested" / "transcripts"
    assert not transcripts_dir.exists()
    save_transcript("vid12345678", _SAMPLE_SEGMENTS, transcripts_dir)
    assert transcripts_dir.exists()


# ---------------------------------------------------------------------------
# transcribe_video
# ---------------------------------------------------------------------------


def test_transcribe_video_success(
    db: sqlite3.Connection, video: Video, tmp_path: Path
) -> None:
    with db:
        insert_video(db, video)

    transcripts_dir = tmp_path / "transcripts"

    with patch("faster_whisper.WhisperModel", return_value=_mock_whisper()):
        result = transcribe_video(video, db, transcripts_dir)

    assert result is not None
    assert result.exists()
    data = json.loads(result.read_text())
    assert len(data["segments"]) == 3

    transcribed = get_videos_by_status(db, "transcribed")
    assert len(transcribed) == 1
    assert transcribed[0].transcript_path is not None


def test_transcribe_video_idempotent(
    db: sqlite3.Connection, video: Video, tmp_path: Path
) -> None:
    with db:
        insert_video(db, video)

    transcripts_dir = tmp_path / "transcripts"
    # Cria transcript pré-existente
    transcripts_dir.mkdir()
    existing = transcripts_dir / "dQw4w9WgXcQ.json"
    existing.write_text(
        json.dumps({"video_id": "dQw4w9WgXcQ", "language": "pt", "segments": []}),
        encoding="utf-8",
    )

    with patch("faster_whisper.WhisperModel") as mock_wm:
        result = transcribe_video(video, db, transcripts_dir)
        mock_wm.assert_not_called()  # Não deve carregar Whisper novamente

    assert result == existing
    assert len(get_videos_by_status(db, "transcribed")) == 1


def test_transcribe_video_dry_run(
    db: sqlite3.Connection, video: Video, tmp_path: Path
) -> None:
    with db:
        insert_video(db, video)

    transcripts_dir = tmp_path / "transcripts"

    with patch("faster_whisper.WhisperModel") as mock_wm:
        result = transcribe_video(video, db, transcripts_dir, dry_run=True)
        mock_wm.assert_not_called()

    assert result is None
    assert len(get_videos_by_status(db, "downloaded")) == 1


def test_transcribe_video_missing_audio_path(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    v = Video(
        video_id="dQw4w9WgXcQ",
        canal_id="flow_podcast",
        title="Teste",
        published_at="2026-05-10T12:00:00Z",
        status="downloaded",
        audio_path=None,
    )
    with db:
        insert_video(db, v)

    transcripts_dir = tmp_path / "transcripts"
    result = transcribe_video(v, db, transcripts_dir)
    assert result is None


def test_transcribe_video_missing_audio_file(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    v = Video(
        video_id="dQw4w9WgXcQ",
        canal_id="flow_podcast",
        title="Teste",
        published_at="2026-05-10T12:00:00Z",
        status="downloaded",
        audio_path=str(tmp_path / "nonexistent.mp3"),
    )
    with db:
        insert_video(db, v)

    result = transcribe_video(v, db, tmp_path / "transcripts")
    assert result is None
    assert len(get_videos_by_status(db, "processing_error")) == 1


def test_transcribe_video_whisper_error(
    db: sqlite3.Connection, video: Video, tmp_path: Path
) -> None:
    with db:
        insert_video(db, video)

    transcripts_dir = tmp_path / "transcripts"

    with patch("faster_whisper.WhisperModel") as mock_wm:
        mock_wm.return_value.transcribe.side_effect = RuntimeError("CUDA OOM")
        result = transcribe_video(video, db, transcripts_dir)

    assert result is None
    assert len(get_videos_by_status(db, "transcribe_error")) == 1
