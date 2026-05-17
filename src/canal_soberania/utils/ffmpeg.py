"""Helpers ffmpeg via subprocess."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class FFmpegError(RuntimeError):
    pass


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise FFmpegError(f"ffmpeg falhou ({result.returncode}): {result.stderr[-500:]}")
    return result


def probe(path: Path) -> dict[str, Any]:
    """Retorna metadados do arquivo via ffprobe."""
    result = _run([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(path),
    ])
    return dict(json.loads(result.stdout))


def get_video_dimensions(path: Path) -> tuple[int, int]:
    """Retorna (width, height) do primeiro stream de vídeo."""
    data = probe(path)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    raise FFmpegError(f"Nenhum stream de vídeo encontrado em {path}")


def cut_video(
    input_path: Path,
    output_path: Path,
    start_s: float,
    end_s: float,
    overwrite: bool = True,
) -> None:
    """Corta vídeo de start_s a end_s sem re-encode (stream copy).

    -ss vem DEPOIS de -i para garantir seek frame-accurate e evitar desync
    áudio/vídeo causado por keyframe misalignment com stream copy.
    """
    duration = end_s - start_s
    args = [
        "ffmpeg",
        *([ "-y"] if overwrite else []),
        "-i", str(input_path),
        "-ss", str(start_s),
        "-t", str(duration),
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        str(output_path),
    ]
    _run(args)


def crop_and_scale(
    input_path: Path,
    output_path: Path,
    crop_x: int,
    crop_w: int,
    crop_h: int,
    out_w: int,
    out_h: int,
    overwrite: bool = True,
) -> None:
    """Recorta e escala vídeo. Usado para reframe 9:16."""
    vf = f"crop={crop_w}:{crop_h}:{crop_x}:0,scale={out_w}:{out_h}"
    args = [
        "ffmpeg",
        *([ "-y"] if overwrite else []),
        "-i", str(input_path),
        "-vf", vf,
        "-c:a", "copy",
        str(output_path),
    ]
    _run(args)


def add_subtitles(
    input_path: Path,
    output_path: Path,
    ass_path: Path,
    overwrite: bool = True,
) -> None:
    """Queima legendas ASS no vídeo."""
    args = [
        "ffmpeg",
        *([ "-y"] if overwrite else []),
        "-i", str(input_path),
        "-vf", f"ass={ass_path}",
        "-c:a", "copy",
        str(output_path),
    ]
    _run(args)


def concat_videos(
    inputs: list[Path],
    output_path: Path,
    overwrite: bool = True,
) -> None:
    """Concatena vídeos usando filter_complex concat."""
    if not inputs:
        raise FFmpegError("Nenhum input para concatenar")

    if len(inputs) == 1:
        import shutil
        shutil.copy2(inputs[0], output_path)
        return

    # Monta lista de inputs e filter_complex
    input_args: list[str] = []
    for p in inputs:
        input_args += ["-i", str(p)]

    n = len(inputs)
    filter_str = "".join(f"[{i}:v][{i}:a]" for i in range(n))
    filter_str += f"concat=n={n}:v=1:a=1[v][a]"

    args = [
        "ffmpeg",
        *([ "-y"] if overwrite else []),
        *input_args,
        "-filter_complex", filter_str,
        "-map", "[v]",
        "-map", "[a]",
        str(output_path),
    ]
    _run(args)


def encode_final(
    input_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int = 30,
    video_bitrate: str = "4M",
    audio_bitrate: str = "192k",
    overwrite: bool = True,
) -> None:
    """Encode final: H.264 + AAC, resolução e fps fixos."""
    vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    args = [
        "ffmpeg",
        *([ "-y"] if overwrite else []),
        "-i", str(input_path),
        "-vf", vf,
        "-r", str(fps),
        "-c:v", "libx264",
        "-b:v", video_bitrate,
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-movflags", "+faststart",
        str(output_path),
    ]
    _run(args)
