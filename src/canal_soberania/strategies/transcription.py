"""Estratégias concretas de transcrição (TranscriptionBackend)."""

from __future__ import annotations

from pathlib import Path

from canal_soberania.core.strategies import TranscriptionSegment


class FasterWhisperBackend:
    """Transcrição local com faster-whisper."""

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: object | None = None

    @property
    def name(self) -> str:
        return f"faster_whisper_{self._model_size}"

    def _get_model(self) -> object:
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        language: str = "pt",
    ) -> list[TranscriptionSegment]:
        model = self._get_model()
        segments_raw, _ = model.transcribe(  # type: ignore[attr-defined]
            str(audio_path),
            language=language,
            word_timestamps=True,
        )
        result: list[TranscriptionSegment] = []
        for seg in segments_raw:
            words = [
                {"word": w.word, "start": w.start, "end": w.end}
                for w in (seg.words or [])
            ]
            result.append(
                TranscriptionSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    words=words,
                )
            )
        return result
