"""Backend Anthropic — wraps LLMClient e OpenRouterClient existentes."""

from __future__ import annotations

import sqlite3

from canal_soberania.llm import LLMClient, LLMResponse, OpenRouterClient


class AnthropicBackend:
    """Delega para LLMClient (claude-*) ou OpenRouterClient (outros modelos)."""

    def __init__(
        self,
        anthropic_api_key: str,
        openrouter_api_key: str = "",
        training_conn: sqlite3.Connection | None = None,
    ) -> None:
        self._anthropic_api_key = anthropic_api_key
        self._openrouter_api_key = openrouter_api_key
        self._training_conn = training_conn
        self._anthropic: LLMClient | None = None
        self._openrouter: OpenRouterClient | None = None

    def _get_client(self, model: str) -> LLMClient | OpenRouterClient:
        if model.startswith("claude-"):
            if self._anthropic is None:
                self._anthropic = LLMClient(self._anthropic_api_key, self._training_conn)
            return self._anthropic
        if self._openrouter is None:
            self._openrouter = OpenRouterClient(self._openrouter_api_key, self._training_conn)
        return self._openrouter

    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        system: str | None = None,
        task: str = "",
    ) -> LLMResponse:
        return self._get_client(model).complete(
            prompt, model=model, max_tokens=max_tokens, system=system, task=task
        )
