"""Stage 8: edita clipes — corte, reframe 9:16, legendas, intro/outro, encode final."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from canal_soberania.config import get_paths, load_settings
from canal_soberania.db import (
    connect,
    get_clips_by_status,
    init_db,
    update_clip_status,
)
from canal_soberania.db import connect as db_connect
from canal_soberania.logger import logger
from canal_soberania.models import Clip
from canal_soberania.utils.ffmpeg import (
    FFmpegError,
    add_subtitles,
    concat_videos,
    crop_and_scale,
    cut_video,
    encode_final,
    get_video_dimensions,
)

# Dimensões de saída
_VERTICAL_W = 1080
_VERTICAL_H = 1920
_HORIZONTAL_W = 1920
_HORIZONTAL_H = 1080
_FPS = 30

# Tags inline para palavra ativa: amarelo (ASS BGR: 0000FFFF) + 8% maior
_WORD_ACTIVE = r"{\c&H0000FFFF&\fscx115\fscy115\bord6}"
_WORD_RESET = r"{\r}"


def _make_ass_header(
    play_w: int, play_h: int, font_size: int, margin_v: int
) -> str:
    return (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {play_w}\nPlayResY: {play_h}\n"
        "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,Arial,{font_size},"
        f"&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,4,0,2,"
        f"80,80,{margin_v},1\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _ts_to_ass(seconds: float) -> str:
    """Converte segundos para formato ASS h:mm:ss.cc."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _words_from_segment(
    text: str, start: float, end: float
) -> list[tuple[float, float, str]]:
    """
    Distribui palavras de um segmento uniformemente no intervalo [start, end].
    Retorna lista de (word_start, word_end, word).
    """
    words = [w for w in text.split() if w]
    if not words:
        return []
    duration = end - start
    word_dur = duration / len(words)
    result: list[tuple[float, float, str]] = []
    for i, word in enumerate(words):
        ws = start + i * word_dur
        we = ws + word_dur
        result.append((ws, we, word))
    return result


def generate_ass(
    segments: list[dict[str, Any]],
    clip_start_s: float,
    output_path: Path,
    words_per_line: int = 3,
    play_w: int = 1080,
    play_h: int = 1920,
    font_size: int = 72,
    margin_v: int = 280,
) -> None:
    """
    Gera arquivo ASS com highlight palavra-por-palavra estilo CapCut.

    Chunks respeitam fronteiras de segmento Whisper (evita cortar nomes compostos).
    Layout de linha é fixo por chunk via \\N explícito (evita reflow ao mudar palavra ativa).
    """
    # Coleta chunks dentro de cada segmento — nunca cruza fronteira de frase
    all_chunks: list[list[tuple[float, float, str]]] = []
    for seg in segments:
        if seg["end"] - clip_start_s <= 0:
            continue

        if seg.get("words"):
            # Timestamps precisos por palavra (requer word_timestamps=True no Whisper)
            raw_words = [
                (max(0.0, w["start"] - clip_start_s), w["end"] - clip_start_s, w["word"])
                for w in seg["words"]
                if w["end"] > clip_start_s and w["word"].strip()
            ]
        else:
            # Fallback: distribuição uniforme (transcrições sem word_timestamps)
            seg_start = max(0.0, seg["start"] - clip_start_s)
            seg_end = seg["end"] - clip_start_s
            raw_words = _words_from_segment(seg["text"], seg_start, seg_end)

        upper_words = [(ws, we, w.strip().upper()) for ws, we, w in raw_words if we > 0]
        for i in range(0, len(upper_words), words_per_line):
            chunk = upper_words[i : i + words_per_line]
            if chunk:
                all_chunks.append(chunk)

    header = _make_ass_header(play_w, play_h, font_size, margin_v)
    lines: list[str] = [header]

    for chunk in all_chunks:
        n = len(chunk)
        # Linha 1: primeira metade (floor); linha 2: resto — layout fixo independente da palavra ativa
        split = n // 2

        for j, (w_start, w_end, _) in enumerate(chunk):
            line1 = [
                f"{_WORD_ACTIVE}{chunk[k][2]}{_WORD_RESET}" if k == j else chunk[k][2]
                for k in range(split)
            ]
            line2 = [
                f"{_WORD_ACTIVE}{chunk[k][2]}{_WORD_RESET}" if k == j else chunk[k][2]
                for k in range(split, n)
            ]
            if line1 and line2:
                text = " ".join(line1) + r"\N" + " ".join(line2)
            else:
                text = " ".join(line1 + line2)

            lines.append(
                f"Dialogue: 0,{_ts_to_ass(w_start)},{_ts_to_ass(w_end)},"
                f"Caption,,0,0,0,,{text}"
            )

    output_path.write_text("\n".join(lines), encoding="utf-8")


def detect_face_crop_x(video_path: Path, sample_time: float = 2.0) -> int | None:
    """
    Extrai um frame e detecta face com mediapipe. Retorna crop_x para centralizar.
    Retorna None se mediapipe não disponível ou face não detectada.
    """
    try:
        import cv2  # type: ignore[import-untyped]
        import mediapipe as mp  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("mediapipe/cv2 não disponível — usando crop central")
        return None

    cap = cv2.VideoCapture(str(video_path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * sample_time))
        ok, frame = cap.read()
    finally:
        cap.release()

    if not ok:
        return None

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = frame_rgb.shape[:2]

    with mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.5
    ) as detector:
        results = detector.process(frame_rgb)

    if not results.detections:
        return None

    # Usa o primeiro rosto detectado (mais proeminente)
    bbox = results.detections[0].location_data.relative_bounding_box
    face_cx = int((bbox.xmin + bbox.width / 2) * w)

    # crop_w para 9:16 a partir de 16:9: target width = h * 9/16
    crop_w = int(h * 9 / 16)
    crop_x = max(0, min(face_cx - crop_w // 2, w - crop_w))
    return crop_x


def edit_clip(
    clip: Clip,
    source_video_path: Path,
    transcript_path: Path | None,
    clips_dir: Path,
    intro_path: Path | None = None,
    outro_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[Path | None, Path | None]:
    """
    Edita um clipe. Retorna (vertical_path, horizontal_path).
    Qualquer um pode ser None se falhar.
    """
    if dry_run:
        logger.info("[dry-run] edit_clip {}", clip.clip_id)
        return None, None

    clips_dir.mkdir(parents=True, exist_ok=True)

    vertical_out = clips_dir / f"{clip.clip_id}_vertical.mp4"
    horizontal_out = clips_dir / f"{clip.clip_id}_horizontal.mp4"

    if vertical_out.exists() and horizontal_out.exists():
        logger.debug("Clipes já existem: {}", clip.clip_id)
        return vertical_out, horizontal_out

    # Carrega segmentos do transcript para gerar legendas
    segments: list[dict[str, Any]] = []
    if transcript_path and transcript_path.exists():
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
        raw_segs = data.get("segments", [])
        # Filtra segmentos dentro do clip
        segments = [
            s for s in raw_segs
            if s["end"] > clip.start_s and s["start"] < clip.end_s
        ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # 1. Cortar vídeo bruto
        cut_path = tmp / "cut.mp4"
        try:
            cut_video(source_video_path, cut_path, clip.start_s, clip.end_s)
        except FFmpegError as exc:
            logger.error("Falha ao cortar {}: {}", clip.clip_id, exc)
            return None, None

        # 2. Detectar face e calcular crop para 9:16
        try:
            src_w, src_h = get_video_dimensions(cut_path)
        except FFmpegError:
            src_w, src_h = 1920, 1080

        target_crop_w = src_h * 9 // 16
        face_crop_x = detect_face_crop_x(cut_path)
        crop_x = face_crop_x if face_crop_x is not None else (src_w - target_crop_w) // 2

        # 3. Versão vertical: crop 9:16 → 1080x1920
        cropped_path = tmp / "cropped.mp4"
        try:
            crop_and_scale(
                cut_path, cropped_path,
                crop_x=crop_x, crop_w=target_crop_w, crop_h=src_h,
                out_w=_VERTICAL_W, out_h=_VERTICAL_H,
            )
        except FFmpegError as exc:
            logger.error("Falha ao recortar {}: {}", clip.clip_id, exc)
            return None, None

        # 4. Gerar e queimar legendas ASS
        ass_path = tmp / f"{clip.clip_id}.ass"
        with_subs_path = tmp / "with_subs.mp4"
        if segments:
            generate_ass(segments, clip.start_s, ass_path)
            try:
                add_subtitles(cropped_path, with_subs_path, ass_path)
            except FFmpegError as exc:
                logger.warning("Falha nas legendas para {} — prosseguindo sem: {}", clip.clip_id, exc)
                shutil.copy2(cropped_path, with_subs_path)
        else:
            shutil.copy2(cropped_path, with_subs_path)

        # 5. Montar lista de partes para concat (intro + conteúdo + outro)
        parts: list[Path] = []
        if intro_path and intro_path.exists():
            parts.append(intro_path)
        parts.append(with_subs_path)
        if outro_path and outro_path.exists():
            parts.append(outro_path)

        concat_path = tmp / "concat.mp4"
        try:
            concat_videos(parts, concat_path)
        except FFmpegError as exc:
            logger.error("Falha ao concatenar {}: {}", clip.clip_id, exc)
            return None, None

        # 6. Encode final vertical 1080x1920
        try:
            encode_final(concat_path, vertical_out, _VERTICAL_W, _VERTICAL_H, _FPS)
        except FFmpegError as exc:
            logger.error("Encode vertical falhou para {}: {}", clip.clip_id, exc)
            return None, None

        # 7. Versão horizontal 1920x1080 com legendas (escala proporcional ao vertical)
        if segments:
            ass_h_path = tmp / f"{clip.clip_id}_h.ass"
            cut_with_subs_path = tmp / "cut_with_subs.mp4"
            # Fonte e margem escalados de 1920px → 1080px (fator 0.5625)
            generate_ass(
                segments, clip.start_s, ass_h_path,
                play_w=_HORIZONTAL_W, play_h=_HORIZONTAL_H,
                font_size=40, margin_v=157,
            )
            try:
                add_subtitles(cut_path, cut_with_subs_path, ass_h_path)
                horizontal_src = cut_with_subs_path
            except FFmpegError as exc:
                logger.warning("Legendas horizontais falharam para {}: {}", clip.clip_id, exc)
                horizontal_src = cut_path
        else:
            horizontal_src = cut_path
        try:
            encode_final(horizontal_src, horizontal_out, _HORIZONTAL_W, _HORIZONTAL_H, _FPS)
        except FFmpegError as exc:
            logger.warning("Encode horizontal falhou para {} (não crítico): {}", clip.clip_id, exc)
            # horizontal é opcional — não bloqueia

    logger.info("Clip editado: {} | vertical={}", clip.clip_id, vertical_out.exists())
    return (
        vertical_out if vertical_out.exists() else None,
        horizontal_out if horizontal_out.exists() else None,
    )


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
        conn = db_connect(paths["db_path"])

    # Procura intro e outro (opcionais)
    data_dir = paths["data_dir"]
    intro_path = data_dir / "intro.mp4"
    outro_path = data_dir / "outro.mp4"

    # Inclui "editing" para recuperar orphans de crash mid-encode
    clips = get_clips_by_status(conn, "identified") + get_clips_by_status(conn, "editing")
    logger.info("edit: {} clipes para processar", len(clips))

    success = failed = 0
    for clip in clips:
        # Busca o vídeo-fonte
        row = conn.execute(
            "SELECT video_path, transcript_path FROM videos WHERE video_id = ?",
            (clip.video_id,),
        ).fetchone()

        if not row or not row["video_path"]:
            logger.error("video_path não encontrado para clipe {}", clip.clip_id)
            with conn:
                update_clip_status(conn, clip.clip_id, "processing_error", "video_path_missing")
            failed += 1
            continue

        source_video = Path(row["video_path"])
        transcript = Path(row["transcript_path"]) if row["transcript_path"] else None

        if not source_video.exists():
            logger.error("Arquivo de vídeo não encontrado: {}", source_video)
            with conn:
                update_clip_status(conn, clip.clip_id, "processing_error", "video_file_missing")
            failed += 1
            continue

        with conn:
            update_clip_status(conn, clip.clip_id, "editing")

        from canal_soberania.utils.heartbeat import HeartbeatKeeper

        with HeartbeatKeeper(conn, "clips", "clip_id", clip.clip_id):
            vertical, horizontal = edit_clip(
                clip=clip,
                source_video_path=source_video,
                transcript_path=transcript,
                clips_dir=paths["clips_dir"],
                intro_path=intro_path if intro_path.exists() else None,
                outro_path=outro_path if outro_path.exists() else None,
                dry_run=dry_run or settings.dry_run,
            )

        if vertical is None and not (dry_run or settings.dry_run):
            with conn:
                update_clip_status(conn, clip.clip_id, "processing_error", "encode_failed")
            failed += 1
            continue

        if not (dry_run or settings.dry_run):
            with conn:
                conn.execute(
                    "UPDATE clips SET clip_path_vertical=?, clip_path_horizontal=?, status='edited' WHERE clip_id=?",
                    (
                        str(vertical) if vertical else None,
                        str(horizontal) if horizontal else None,
                        clip.clip_id,
                    ),
                )
            success += 1

    logger.info("edit concluído | ok={} falhas={}", success, failed)
