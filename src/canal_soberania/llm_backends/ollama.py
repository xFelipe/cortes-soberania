"""Backend Ollama — chama API OpenAI-compatible em localhost:11434."""

from __future__ import annotations

import json
import socket
import sqlite3
import urllib.error
import urllib.request

from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from canal_soberania.llm import LLMResponse, _log_training  # noqa: PLC2701
from canal_soberania.logger import logger

_DEFAULT_BASE_URL = "http://localhost:11434/v1/chat/completions"


def _is_retriable(exc: BaseException) -> bool:
    return isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 500, 502, 503, 504)


class OllamaBackend:
    """Ollama via API OpenAI-compatible. Ignora o parâmetro `model` do caller;
    usa sempre o modelo configurado em `__init__`."""

    def __init__(
        self,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        training_conn: sqlite3.Connection | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._training_conn = training_conn

    @retry(
        retry=(
            retry_if_exception_type((urllib.error.URLError, socket.timeout, json.JSONDecodeError))
            | retry_if_exception(_is_retriable)
        ),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _call_api(self, req: urllib.request.Request) -> dict[str, object]:
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
            return dict(json.loads(resp.read()))

    def complete(
        self,
        prompt: str,
        model: str,  # aceito mas ignorado — usa self._model
        max_tokens: int = 1024,
        system: str | None = None,
        task: str = "",
    ) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        logger.debug(
            "Ollama call | model={} | task={} | prompt_len={}", self._model, task, len(prompt)
        )

        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }).encode()
        req = urllib.request.Request(  # noqa: S310
            self._base_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        data = self._call_api(req)

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError(f"Ollama: resposta inesperada: {str(data)[:200]}")

        from typing import cast
        first_choice = cast(dict[str, object], choices[0])
        msg = cast(dict[str, object], first_choice["message"])
        text: str = str(msg["content"])
        usage_raw = data.get("usage", {})
        usage: dict[str, object] = cast(dict[str, object], usage_raw) if isinstance(usage_raw, dict) else {}
        raw_in = usage.get("prompt_tokens", 0)
        raw_out = usage.get("completion_tokens", 0)
        tokens_in: int = raw_in if isinstance(raw_in, int) else 0
        tokens_out: int = raw_out if isinstance(raw_out, int) else 0

        logger.debug(
            "Ollama done | model={} | in={} out={}", self._model, tokens_in, tokens_out
        )

        if self._training_conn is not None and task:
            _log_training(
                self._training_conn, task, prompt, text,
                self._model, system, tokens_in, tokens_out, cost_usd=0.0,
            )

        return LLMResponse(
            text=text,
            model=self._model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=0.0,
        )
