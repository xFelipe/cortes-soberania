"""Backend Hybrid — Ollama para triagem rápida, Anthropic para análise profunda."""

from __future__ import annotations

from canal_soberania.llm import LLMResponse
from canal_soberania.llm_backends.anthropic import AnthropicBackend
from canal_soberania.llm_backends.ollama import OllamaBackend

# Tasks que usam o backend rápido (Ollama Qwen 14B)
_FAST_TASKS: frozenset[str] = frozenset({"triage_metadata", "triage_caption"})


class HybridBackend:
    """Roteia por task: triagem rápida → Ollama; análise profunda → Anthropic."""

    def __init__(self, fast: OllamaBackend, deep: AnthropicBackend) -> None:
        self._fast = fast
        self._deep = deep

    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        system: str | None = None,
        task: str = "",
    ) -> LLMResponse:
        backend = self._fast if task in _FAST_TASKS else self._deep
        return backend.complete(prompt, model=model, max_tokens=max_tokens, system=system, task=task)
