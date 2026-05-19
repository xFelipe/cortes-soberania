"""Interface LLMBackend — Protocol estrutural para backends de LLM."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from canal_soberania.llm import LLMResponse


@runtime_checkable
class LLMBackend(Protocol):
    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        system: str | None = None,
        task: str = "",
    ) -> LLMResponse: ...
