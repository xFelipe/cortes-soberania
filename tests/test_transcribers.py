"""Testes para canal_soberania.transcribers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from canal_soberania.config import Settings
from canal_soberania.transcribers import (
    FasterWhisperLocal,
    GroqWhisperTranscriber,
    OpenAIWhisperTranscriber,
    Transcriber,
    get_transcriber,
)


def _fake_segments() -> list[dict[str, Any]]:
    return [{"start": 0.0, "end": 5.0, "text": "Olá mundo"}]


# ---------------------------------------------------------------------------
# Transcriber Protocol (structural check)
# ---------------------------------------------------------------------------


class TestTranscriberProtocol:
    def test_faster_whisper_local_satisfies_protocol(self) -> None:
        t = FasterWhisperLocal()
        assert isinstance(t, Transcriber)

    def test_groq_satisfies_protocol(self) -> None:
        t = GroqWhisperTranscriber(api_key="k")
        assert isinstance(t, Transcriber)

    def test_openai_satisfies_protocol(self) -> None:
        t = OpenAIWhisperTranscriber(api_key="k")
        assert isinstance(t, Transcriber)


# ---------------------------------------------------------------------------
# FasterWhisperLocal
# ---------------------------------------------------------------------------


class TestFasterWhisperLocal:
    def test_delegates_to_transcribe_audio(self, tmp_path: Path) -> None:
        audio = tmp_path / "audio.mp3"
        audio.touch()
        t = FasterWhisperLocal(model_size="tiny", device="cpu", compute_type="int8")

        with patch(
            "canal_soberania.stages.transcribe.transcribe_audio",
            return_value=_fake_segments(),
        ) as mock_fn:
            result = t.transcribe(audio)

        mock_fn.assert_called_once_with(audio, model_size="tiny", device="cpu", compute_type="int8")
        assert result == _fake_segments()

    def test_cuda_config(self) -> None:
        t = FasterWhisperLocal(device="cuda", compute_type="float16")
        assert t._device == "cuda"
        assert t._compute_type == "float16"


# ---------------------------------------------------------------------------
# Factory get_transcriber
# ---------------------------------------------------------------------------


class TestGetTranscriber:
    def test_local_cpu_returns_faster_whisper(self) -> None:
        s = Settings(whisper_backend="local_cpu")
        t = get_transcriber(s)
        assert isinstance(t, FasterWhisperLocal)
        assert t._device == "cpu"

    def test_local_cuda_returns_faster_whisper_cuda(self) -> None:
        s = Settings(whisper_backend="local_cuda")
        t = get_transcriber(s)
        assert isinstance(t, FasterWhisperLocal)
        assert t._device == "cuda"
        assert t._compute_type == "float16"

    def test_groq_returns_groq_transcriber(self) -> None:
        s = Settings(whisper_backend="groq", groq_api_key="groqkey")
        t = get_transcriber(s)
        assert isinstance(t, GroqWhisperTranscriber)
        assert t._api_key == "groqkey"

    def test_openai_returns_openai_transcriber(self) -> None:
        s = Settings(whisper_backend="openai", openai_api_key="oaikey")
        t = get_transcriber(s)
        assert isinstance(t, OpenAIWhisperTranscriber)
        assert t._api_key == "oaikey"

    def test_unknown_backend_falls_back_to_cpu(self) -> None:
        s = Settings(whisper_backend="inexistente")
        t = get_transcriber(s)
        assert isinstance(t, FasterWhisperLocal)
        assert t._device == "cpu"
