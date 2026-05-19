"""Interface Transcriber — Protocol estrutural para backends de transcrição."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> list[dict[str, Any]]:
        """Transcreve áudio. Retorna lista de segmentos [{start, end, text, words?}]."""
        ...
