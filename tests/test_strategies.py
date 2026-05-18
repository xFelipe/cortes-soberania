"""Testes para os Strategy protocols e implementações concretas."""

from __future__ import annotations

from pathlib import Path

import pytest

from canal_soberania.core.strategies import CropParams, ReframeStrategy, TranscriptionBackend
from canal_soberania.strategies.reframe import CenterCropReframe, FaceDetectionReframe


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


def test_center_crop_satisfies_reframe_protocol() -> None:
    assert isinstance(CenterCropReframe(), ReframeStrategy)


def test_face_detection_satisfies_reframe_protocol() -> None:
    assert isinstance(FaceDetectionReframe(), ReframeStrategy)


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


