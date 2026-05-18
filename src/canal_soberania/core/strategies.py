"""Protocolos Strategy para os pontos variáveis do pipeline.

Cada protocolo define a interface que implementações concretas devem cumprir,
permitindo trocar algoritmos sem alterar o core (ex: reframe por face detection
vs. crop central, Whisper local vs. cloud API).

Upload/distribuição para plataformas externas → ver core/platforms.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# ReframeStrategy — define como recortar o frame para 9:16
# ---------------------------------------------------------------------------


@dataclass
class CropParams:
    x: int
    y: int
    width: int
    height: int


@runtime_checkable
class ReframeStrategy(Protocol):
    """Determina os parâmetros de crop para reencadrar um vídeo em 9:16."""

    @property
    def name(self) -> str: ...

    def get_crop_params(
        self,
        frame: Any,          # np.ndarray em produção; Any para não forçar dep de numpy no protocolo
        source_width: int,
        source_height: int,
        target_width: int = 1080,
        target_height: int = 1920,
    ) -> CropParams: ...


# ---------------------------------------------------------------------------
# TranscriptionBackend — abstrai faster-whisper, cloud API, etc.
# ---------------------------------------------------------------------------


@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str
    words: list[dict[str, Any]]


@runtime_checkable
class TranscriptionBackend(Protocol):
    """Transcreve áudio e retorna segmentos com timestamps."""

    @property
    def name(self) -> str: ...

    def transcribe(
        self,
        audio_path: Path,
        language: str = "pt",
    ) -> list[TranscriptionSegment]: ...
