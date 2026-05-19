"""Testes para canal_soberania.llm_backends."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.config import Settings
from canal_soberania.llm import LLMResponse
from canal_soberania.llm_backends import (
    AnthropicBackend,
    HybridBackend,
    LLMBackend,
    OllamaBackend,
    get_llm_backend,
)
from canal_soberania.llm_backends.hybrid import _FAST_TASKS


def _fake_response(model: str = "claude-haiku-4-5-20251001") -> LLMResponse:
    return LLMResponse(text='{"ok": true}', model=model, tokens_in=10, tokens_out=5, cost_usd=0.0)


# ---------------------------------------------------------------------------
# LLMBackend Protocol (structural check)
# ---------------------------------------------------------------------------


class TestLLMBackendProtocol:
    def test_anthropic_satisfies_protocol(self) -> None:
        backend = AnthropicBackend(anthropic_api_key="k")
        assert isinstance(backend, LLMBackend)

    def test_ollama_satisfies_protocol(self) -> None:
        backend = OllamaBackend(model="qwen2.5:14b-instruct-q4_K_M")
        assert isinstance(backend, LLMBackend)

    def test_hybrid_satisfies_protocol(self) -> None:
        fast = OllamaBackend(model="qwen2.5:14b-instruct-q4_K_M")
        deep = AnthropicBackend(anthropic_api_key="k")
        backend = HybridBackend(fast=fast, deep=deep)
        assert isinstance(backend, LLMBackend)


# ---------------------------------------------------------------------------
# AnthropicBackend
# ---------------------------------------------------------------------------


class TestAnthropicBackend:
    def test_delegates_claude_to_llm_client(self) -> None:
        backend = AnthropicBackend(anthropic_api_key="key123")
        expected = _fake_response()
        with patch("canal_soberania.llm_backends.anthropic.LLMClient") as MockClient:
            instance = MockClient.return_value
            instance.complete.return_value = expected
            result = backend.complete("prompt", model="claude-haiku-4-5-20251001", task="t")

        instance.complete.assert_called_once_with(
            "prompt", model="claude-haiku-4-5-20251001", max_tokens=1024, system=None, task="t"
        )
        assert result == expected

    def test_delegates_non_claude_to_openrouter(self) -> None:
        backend = AnthropicBackend(anthropic_api_key="k", openrouter_api_key="orkey")
        expected = _fake_response(model="google/gemini-2.0-flash-001")
        with patch("canal_soberania.llm_backends.anthropic.OpenRouterClient") as MockOR:
            instance = MockOR.return_value
            instance.complete.return_value = expected
            result = backend.complete("prompt", model="google/gemini-2.0-flash-001")

        instance.complete.assert_called_once()
        assert result == expected

    def test_reuses_client_instance(self) -> None:
        backend = AnthropicBackend(anthropic_api_key="k")
        with patch("canal_soberania.llm_backends.anthropic.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = _fake_response()
            backend.complete("p", model="claude-haiku-4-5-20251001")
            backend.complete("p2", model="claude-haiku-4-5-20251001")

        assert MockClient.call_count == 1


# ---------------------------------------------------------------------------
# OllamaBackend
# ---------------------------------------------------------------------------


class TestOllamaBackend:
    def _mock_response_data(self, text: str = "ok", model: str = "qwen2.5:14b") -> bytes:
        data = {
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        return json.dumps(data).encode()

    def test_ignores_model_param_uses_own_model(self) -> None:
        backend = OllamaBackend(model="qwen2.5:14b-instruct-q4_K_M")
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = self._mock_response_data()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = backend.complete("prompt", model="claude-haiku-4-5-20251001", task="test")

        assert result.model == "qwen2.5:14b-instruct-q4_K_M"
        assert result.cost_usd == 0.0

    def test_returns_llm_response(self) -> None:
        backend = OllamaBackend(model="qwen2.5:14b-instruct-q4_K_M")
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = self._mock_response_data(text="resposta")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = backend.complete("prompt", model="irrelevante")

        assert result.text == "resposta"
        assert result.tokens_in == 10
        assert result.tokens_out == 5

    def test_raises_on_empty_choices(self) -> None:
        backend = OllamaBackend(model="qwen2.5:14b-instruct-q4_K_M")
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps({"choices": []}).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(ValueError, match="Ollama"):
                backend.complete("prompt", model="x")


# ---------------------------------------------------------------------------
# HybridBackend
# ---------------------------------------------------------------------------


class TestHybridBackend:
    def _make_hybrid(self) -> tuple[HybridBackend, MagicMock, MagicMock]:
        fast = MagicMock(spec=OllamaBackend)
        fast.complete.return_value = _fake_response(model="qwen2.5:14b")
        deep = MagicMock(spec=AnthropicBackend)
        deep.complete.return_value = _fake_response(model="claude-sonnet-4-6")
        return HybridBackend(fast=fast, deep=deep), fast, deep  # type: ignore[arg-type]

    def test_fast_tasks_use_ollama(self) -> None:
        hybrid, fast, deep = self._make_hybrid()
        for task in _FAST_TASKS:
            hybrid.complete("p", model="m", task=task)
        assert fast.complete.call_count == len(_FAST_TASKS)
        deep.complete.assert_not_called()

    def test_deep_tasks_use_anthropic(self) -> None:
        hybrid, fast, deep = self._make_hybrid()
        for task in ("triage_transcript", "find_clips", "metadata"):
            hybrid.complete("p", model="m", task=task)
        assert deep.complete.call_count == 3
        fast.complete.assert_not_called()

    def test_unknown_task_uses_deep(self) -> None:
        hybrid, fast, deep = self._make_hybrid()
        hybrid.complete("p", model="m", task="")
        deep.complete.assert_called_once()
        fast.complete.assert_not_called()


# ---------------------------------------------------------------------------
# Factory get_llm_backend
# ---------------------------------------------------------------------------


class TestGetLlmBackend:
    def test_returns_anthropic_backend(self) -> None:
        s = Settings(llm_backend="anthropic", anthropic_api_key="k")
        result = get_llm_backend(s)
        assert isinstance(result, AnthropicBackend)

    def test_returns_ollama_backend(self) -> None:
        s = Settings(llm_backend="ollama", ollama_model_triage="qwen2.5:14b-instruct-q4_K_M")
        result = get_llm_backend(s)
        assert isinstance(result, OllamaBackend)

    def test_returns_hybrid_backend(self) -> None:
        s = Settings(llm_backend="hybrid", anthropic_api_key="k")
        result = get_llm_backend(s)
        assert isinstance(result, HybridBackend)

    def test_unknown_backend_falls_back_to_anthropic(self) -> None:
        s = Settings(llm_backend="inexistente", anthropic_api_key="k")
        result = get_llm_backend(s)
        assert isinstance(result, AnthropicBackend)
