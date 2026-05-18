"""Estratégias concretas de reframe (ReframeStrategy)."""

from __future__ import annotations

from typing import Any

from canal_soberania.core.strategies import CropParams
from canal_soberania.logger import logger


class CenterCropReframe:
    """Recorta no centro do frame — fallback quando não há detecção de face."""

    @property
    def name(self) -> str:
        return "center_crop"

    def get_crop_params(
        self,
        frame: Any,
        source_width: int,
        source_height: int,
        target_width: int = 1080,
        target_height: int = 1920,
    ) -> CropParams:
        crop_w = int(source_height * target_width / target_height)
        crop_w = min(crop_w, source_width)
        x = (source_width - crop_w) // 2
        return CropParams(x=x, y=0, width=crop_w, height=source_height)


class FaceDetectionReframe:
    """Centraliza o crop no rosto detectado via mediapipe; fallback para centro."""

    @property
    def name(self) -> str:
        return "face_detection"

    def get_crop_params(
        self,
        frame: Any,
        source_width: int,
        source_height: int,
        target_width: int = 1080,
        target_height: int = 1920,
    ) -> CropParams:
        crop_w = int(source_height * target_width / target_height)
        crop_w = min(crop_w, source_width)
        face_cx: int | None = None

        try:
            import cv2
            import mediapipe as mp  # type: ignore[import-untyped]

            if frame is None:
                raise ValueError("frame nulo")

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            with mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True, max_num_faces=1
            ) as fm:
                results = fm.process(rgb)
                if results.multi_face_landmarks:
                    lms = results.multi_face_landmarks[0].landmark
                    xs = [lm.x for lm in lms]
                    face_cx = int(sum(xs) / len(xs) * source_width)
        except Exception as exc:
            logger.debug("face_detection: mediapipe indisponível ou frame inválido → fallback ({})", exc)

        if face_cx is None:
            x = (source_width - crop_w) // 2
        else:
            x = max(0, min(face_cx - crop_w // 2, source_width - crop_w))

        return CropParams(x=x, y=0, width=crop_w, height=source_height)
