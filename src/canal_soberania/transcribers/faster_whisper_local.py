"""Transcriber local com faster-whisper (CPU ou CUDA)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class FasterWhisperLocal:
    """Wraps transcribe_audio() de stages/transcribe.py.

    Carrega o modelo uma única vez e reutiliza entre chamadas.
    device='cuda' | 'cpu'; compute_type='float16' (CUDA) | 'int8' (CPU).
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type

    def transcribe(self, audio_path: Path) -> list[dict[str, Any]]:
        from canal_soberania.stages.transcribe import transcribe_audio

        return transcribe_audio(
            audio_path,
            model_size=self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
