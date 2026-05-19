"""Backends plugáveis de transcrição — factory pública."""

from __future__ import annotations

from canal_soberania.transcribers.base import Transcriber
from canal_soberania.transcribers.faster_whisper_local import FasterWhisperLocal
from canal_soberania.transcribers.groq_whisper import GroqWhisperTranscriber
from canal_soberania.transcribers.openai_whisper import OpenAIWhisperTranscriber

__all__ = [
    "FasterWhisperLocal",
    "GroqWhisperTranscriber",
    "OpenAIWhisperTranscriber",
    "Transcriber",
    "get_transcriber",
]


def get_transcriber(settings: object) -> FasterWhisperLocal | GroqWhisperTranscriber | OpenAIWhisperTranscriber:
    """Retorna o transcriber correto com base em settings.whisper_backend."""
    from canal_soberania.config import Settings

    s: Settings = settings  # type: ignore[assignment]

    backend = s.whisper_backend.lower()

    if backend == "local_cuda":
        return FasterWhisperLocal(
            model_size=s.whisper_model,
            device="cuda",
            compute_type="float16",
        )

    if backend == "groq":
        return GroqWhisperTranscriber(api_key=s.groq_api_key)

    if backend == "openai":
        return OpenAIWhisperTranscriber(api_key=s.openai_api_key)

    # Padrão: local_cpu
    return FasterWhisperLocal(
        model_size=s.whisper_model,
        device="cpu",
        compute_type="int8",
    )
