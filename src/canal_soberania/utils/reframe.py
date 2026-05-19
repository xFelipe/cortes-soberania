"""Utilitários de reframe 9:16: detecção de rosto para crop_x."""

from __future__ import annotations

import tempfile
from pathlib import Path

from canal_soberania.logger import logger


def detect_face_crop_x(video_path: Path, sample_time: float = 2.0) -> int | None:
    """
    Extrai um frame e detecta face com mediapipe. Retorna crop_x para centralizar.
    Retorna None se mediapipe não disponível ou face não detectada.
    """
    try:
        import cv2
        import mediapipe as mp
        if not hasattr(mp, "solutions"):
            raise ImportError("mediapipe.solutions indisponível nesta versão")
    except ImportError as exc:
        logger.debug("mediapipe/cv2 não disponível — usando crop central ({})", exc)
        return None

    from canal_soberania.utils.ffmpeg import _av1_decoder_args, _run

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as _f:
        frame_path = Path(_f.name)
    try:
        _run([
            "ffmpeg", "-y",
            "-hwaccel", "none",
            *_av1_decoder_args(video_path),
            "-ss", str(sample_time),
            "-i", str(video_path),
            "-frames:v", "1",
            str(frame_path),
        ], check=False)
        frame_bgr = cv2.imread(str(frame_path))
    finally:
        frame_path.unlink(missing_ok=True)

    if frame_bgr is None:
        return None

    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w = frame_rgb.shape[:2]

    with mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.5
    ) as detector:
        results = detector.process(frame_rgb)

    if not results.detections:
        return None

    bbox = results.detections[0].location_data.relative_bounding_box
    face_cx = int((bbox.xmin + bbox.width / 2) * w)

    crop_w = int(h * 9 / 16)
    crop_x: int = max(0, min(face_cx - crop_w // 2, int(w) - crop_w))
    return crop_x
