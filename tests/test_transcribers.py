"""Testes para canal_soberania.transcribers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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


# ---------------------------------------------------------------------------
# Helpers para mockar urllib.request.urlopen
# ---------------------------------------------------------------------------


import contextlib
import json as _json
import urllib.request


def _mock_urlopen(response_data: dict[str, Any]):  # type: ignore[type-arg]
    """Retorna um context manager que simula urlopen retornando JSON."""

    class _FakeResponse:
        def read(self) -> bytes:
            return _json.dumps(response_data).encode()

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    return lambda *a, **kw: _FakeResponse()


# ---------------------------------------------------------------------------
# GroqWhisperTranscriber
# ---------------------------------------------------------------------------


class TestGroqWhisperTranscriber:
    def test_transcribe_with_words_single_segment(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"fake-audio")

        response = {
            "words": [
                {"start": 0.0, "end": 0.5, "word": "Olá"},
                {"start": 0.6, "end": 1.0, "word": "mundo"},
            ]
        }
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen(response))

        t = GroqWhisperTranscriber(api_key="key")
        segs = t.transcribe(audio)

        assert len(segs) == 1
        assert segs[0]["text"] == "Olá mundo"
        assert segs[0]["start"] == 0.0
        assert segs[0]["end"] == 1.0

    def test_transcribe_words_split_by_gap(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"x")

        response = {
            "words": [
                {"start": 0.0, "end": 0.5, "word": "A"},
                # gap > 1.5s → new segment
                {"start": 2.5, "end": 3.0, "word": "B"},
            ]
        }
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen(response))

        t = GroqWhisperTranscriber(api_key="key")
        segs = t.transcribe(audio)

        assert len(segs) == 2
        assert segs[0]["text"] == "A"
        assert segs[1]["text"] == "B"

    def test_transcribe_words_split_by_long_text(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"x")

        long_word = "a" * 501
        response = {
            "words": [
                {"start": 0.0, "end": 0.5, "word": long_word},
                {"start": 0.6, "end": 1.0, "word": "fim"},
            ]
        }
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen(response))

        t = GroqWhisperTranscriber(api_key="key")
        segs = t.transcribe(audio)

        assert len(segs) == 2

    def test_transcribe_fallback_no_words_with_text(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"x")

        response = {"words": [], "text": "Texto completo.", "duration": 10.5}
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen(response))

        t = GroqWhisperTranscriber(api_key="key")
        segs = t.transcribe(audio)

        assert len(segs) == 1
        assert segs[0]["text"] == "Texto completo."
        assert segs[0]["end"] == 10.5

    def test_transcribe_fallback_empty_text_returns_empty(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"x")

        response = {"words": [], "text": ""}
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen(response))

        t = GroqWhisperTranscriber(api_key="key")
        segs = t.transcribe(audio)

        assert segs == []


# ---------------------------------------------------------------------------
# OpenAIWhisperTranscriber  (mesma lógica, URL diferente)
# ---------------------------------------------------------------------------


class TestOpenAIWhisperTranscriber:
    def test_transcribe_with_words(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"fake-audio")

        response = {
            "words": [
                {"start": 1.0, "end": 1.5, "word": "Soberania"},
                {"start": 1.6, "end": 2.0, "word": "nacional"},
            ]
        }
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen(response))

        t = OpenAIWhisperTranscriber(api_key="key")
        segs = t.transcribe(audio)

        assert len(segs) == 1
        assert "Soberania" in segs[0]["text"]

    def test_transcribe_fallback_text_only(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"x")

        response = {"words": [], "text": "Olá.", "duration": 5.0}
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen(response))

        t = OpenAIWhisperTranscriber(api_key="key")
        segs = t.transcribe(audio)

        assert segs[0]["text"] == "Olá."
        assert segs[0]["end"] == 5.0

    def test_transcribe_split_by_gap(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"x")

        response = {
            "words": [
                {"start": 0.0, "end": 0.3, "word": "X"},
                {"start": 5.0, "end": 5.3, "word": "Y"},
            ]
        }
        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen(response))

        t = OpenAIWhisperTranscriber(api_key="key")
        segs = t.transcribe(audio)

        assert len(segs) == 2
