"""Stage 5: transcrição de áudio com faster-whisper (PT-BR)."""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from canal_soberania.config import get_paths, load_settings
from canal_soberania.db import (
    connect,
    get_videos_by_statuses,
    init_db,
    update_video_paths,
    update_video_status,
)
from canal_soberania.logger import logger
from canal_soberania.models import Video


def _preload_cuda_from_venv() -> None:
    """Precarrega libs CUDA do site-packages antes do ctranslate2 chamar dlopen.

    ctranslate2 faz dlopen("libcublas.so.12") sem caminho absoluto. Quando as
    libs vêm do wheel nvidia-cublas-cu12, elas ficam em site-packages/nvidia/*/lib
    e não estão no LD_LIBRARY_PATH padrão. Carregar via ctypes.CDLL com o caminho
    completo coloca a lib no cache do dynamic linker; a chamada interna do
    ctranslate2 as encontra sem precisar alterar variáveis de ambiente.
    """
    sp = (
        Path(sys.executable).parent.parent
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    candidates = [
        sp / "nvidia" / "cublas" / "lib" / "libcublas.so.12",
        sp / "nvidia" / "cudnn" / "lib" / "libcudnn.so.9",
        sp / "nvidia" / "cudnn" / "lib" / "libcudnn.so.8",
        sp / "nvidia" / "cuda_runtime" / "lib" / "libcudart.so.12",
    ]
    for lib in candidates:
        if lib.exists():
            with contextlib.suppress(OSError):
                ctypes.CDLL(str(lib))


def _format_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


_WHISPER_SAMPLE_RATE = 16_000


def _decode_audio(audio_path: Path) -> np.ndarray:
    """Decodifica áudio para float32 via ffmpeg.

    Bypassa o decoder interno do faster-whisper (PyAV), que falha quando o
    arquivo tem metadados ID3 com caracteres não-ASCII (ã, é, etc.).
    """
    cmd = [
        "ffmpeg", "-nostdin", "-threads", "0",
        "-i", str(audio_path),
        "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le",
        "-ar", str(_WHISPER_SAMPLE_RATE), "-",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)  # noqa: S603
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe_audio(
    audio_path: Path,
    model_size: str = "large-v3",
    device: str = "cpu",
    compute_type: str = "int8",
) -> list[dict[str, Any]]:
    """
    Roda faster-whisper e retorna lista de segmentos
    [{start: float, end: float, text: str}].
    """
    _preload_cuda_from_venv()
    from faster_whisper import WhisperModel

    logger.info("Carregando Whisper {} ({}/{})", model_size, device, compute_type)
    import os
    cpu_threads = int(os.environ.get("WHISPER_CPU_THREADS", os.cpu_count() or 4))
    model = WhisperModel(model_size, device=device, compute_type=compute_type, cpu_threads=cpu_threads)

    logger.info("Transcrevendo {}...", audio_path.name)
    audio_array = _decode_audio(audio_path)
    segments_iter, info = model.transcribe(
        audio_array,
        language="pt",
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
    )

    logger.debug("Idioma detectado: {} (prob={:.2f})", info.language, info.language_probability)

    segments: list[dict[str, Any]] = []
    for seg in segments_iter:
        seg_data: dict[str, Any] = {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        if seg.words:
            seg_data["words"] = [
                {"start": w.start, "end": w.end, "word": w.word.strip()}
                for w in seg.words
                if w.word.strip()
            ]
        segments.append(seg_data)

    logger.info("  {} segmentos transcritos", len(segments))
    return segments


def save_transcript(
    video_id: str,
    segments: list[dict[str, Any]],
    transcripts_dir: Path,
    language: str = "pt",
) -> Path:
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    final_path = transcripts_dir / f"{video_id}.json"
    data = {"video_id": video_id, "language": language, "segments": segments}
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    # Write atômico: garante que crash mid-write não deixe JSON corrompido
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=transcripts_dir,
        prefix=f".{video_id}.",
        suffix=".json.tmp",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(payload)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, final_path)
    return final_path


def format_segments_for_prompt(segments: list[dict[str, Any]], max_chars: int = 12000) -> str:
    """Converte segmentos para texto legível pelo LLM com timestamps."""
    lines: list[str] = []
    for seg in segments:
        ts = f"[{_format_ts(seg['start'])} → {_format_ts(seg['end'])}]"
        lines.append(f"{ts} {seg['text']}")
    text = "\n".join(lines)
    return text[:max_chars]


def transcribe_video(
    video: Video,
    conn: sqlite3.Connection,
    transcripts_dir: Path,
    model_size: str = "large-v3",
    device: str = "cpu",
    compute_type: str = "int8",
    dry_run: bool = False,
) -> Path | None:
    """
    Transcreve o áudio de um vídeo. Retorna o path do JSON ou None em caso de erro.
    """
    if not video.audio_path:
        logger.error("audio_path vazio para {} — pulando", video.video_id)
        return None

    audio_path = Path(video.audio_path)
    if not audio_path.exists():
        logger.error("Arquivo de áudio não encontrado: {}", audio_path)
        with conn:
            update_video_status(
                conn, video.video_id, "processing_error", "audio_file_missing"
            )
        return None

    transcript_path = transcripts_dir / f"{video.video_id}.json"
    if transcript_path.exists():
        logger.debug("Transcrição já existe: {}", transcript_path)
        if not dry_run:
            with conn:
                update_video_paths(
                    conn, video.video_id, transcript_path=str(transcript_path)
                )
                update_video_status(conn, video.video_id, "transcribed")
        return transcript_path

    if dry_run:
        logger.info("[dry-run] transcribe {}", video.video_id)
        return None

    with conn:
        update_video_status(conn, video.video_id, "transcribing")

    from canal_soberania.utils.heartbeat import HeartbeatKeeper

    try:
        with HeartbeatKeeper(conn, "videos", "video_id", video.video_id):
            segments = transcribe_audio(audio_path, model_size, device, compute_type)
    except Exception as exc:
        logger.error("Whisper error para {}: {}", video.video_id, exc)
        with conn:
            update_video_status(
                conn, video.video_id, "transcribe_error", f"whisper_error: {exc}"
            )
        return None

    transcript_path = save_transcript(video.video_id, segments, transcripts_dir)

    with conn:
        update_video_paths(conn, video.video_id, transcript_path=str(transcript_path))
        update_video_status(conn, video.video_id, "transcribed")

    logger.info(
        "Transcrição concluída: {} | segmentos={}", video.video_id, len(segments)
    )
    return transcript_path


def run(
    conn: sqlite3.Connection | None = None,
    dry_run: bool = False,
) -> None:
    """Entry point chamado pelo CLI."""
    settings = load_settings()
    paths = get_paths(settings)

    if conn is None:
        if not paths["db_path"].exists():
            init_db(paths["db_path"], paths["schema_path"])
        conn = connect(paths["db_path"])

    videos = get_videos_by_statuses(conn, ["downloaded", "transcribing", "transcribe_error"])
    logger.info("transcribe: {} vídeos para processar", len(videos))
    if not videos:
        return

    transcripts_dir = paths["transcripts_dir"]
    success = failed = 0

    for video in videos:
        result = transcribe_video(
            video=video,
            conn=conn,
            transcripts_dir=transcripts_dir,
            model_size=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            dry_run=dry_run or settings.dry_run,
        )
        if result is not None:
            success += 1
        elif not (dry_run or settings.dry_run):
            failed += 1

    logger.info("transcribe concluído | ok={} falhas={}", success, failed)
