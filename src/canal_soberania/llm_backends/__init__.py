"""Backends plugáveis de LLM — factory pública."""

from __future__ import annotations

import sqlite3

from canal_soberania.llm_backends.anthropic import AnthropicBackend
from canal_soberania.llm_backends.base import LLMBackend
from canal_soberania.llm_backends.hybrid import HybridBackend
from canal_soberania.llm_backends.ollama import OllamaBackend

__all__ = ["AnthropicBackend", "HybridBackend", "LLMBackend", "OllamaBackend", "get_llm_backend"]


def get_llm_backend(
    settings: object,
    training_conn: sqlite3.Connection | None = None,
) -> AnthropicBackend | OllamaBackend | HybridBackend:
    """Retorna o backend correto com base em settings.llm_backend."""
    from canal_soberania.config import Settings

    s: Settings = settings  # type: ignore[assignment]

    backend_name = s.llm_backend.lower()

    if backend_name == "anthropic":
        return AnthropicBackend(
            anthropic_api_key=s.anthropic_api_key,
            openrouter_api_key=s.openrouter_api_key,
            training_conn=training_conn,
        )

    if backend_name == "ollama":
        return OllamaBackend(
            model=s.ollama_model_triage,
            base_url=s.ollama_base_url,
            training_conn=training_conn,
        )

    if backend_name == "hybrid":
        fast = OllamaBackend(
            model=s.ollama_model_triage,
            base_url=s.ollama_base_url,
            training_conn=training_conn,
        )
        deep = AnthropicBackend(
            anthropic_api_key=s.anthropic_api_key,
            openrouter_api_key=s.openrouter_api_key,
            training_conn=training_conn,
        )
        return HybridBackend(fast=fast, deep=deep)

    # Fallback seguro
    return AnthropicBackend(
        anthropic_api_key=s.anthropic_api_key,
        openrouter_api_key=s.openrouter_api_key,
        training_conn=training_conn,
    )
