"""Clientes LLM: Anthropic (direto) e OpenRouter (todos os demais modelos)."""

from __future__ import annotations

import json
import re
import socket
import sqlite3
import urllib.error
import urllib.request

import anthropic
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, retry_if_exception_type, stop_after_attempt, wait_exponential

from canal_soberania.logger import logger

# ---------------------------------------------------------------------------
# Tabela de preços por milhão de tokens (USD)
# ---------------------------------------------------------------------------

_COST_TABLE: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-haiku-4-5-20251001":      {"in": 1.00,  "out": 5.00},
    "claude-haiku-4-5":               {"in": 1.00,  "out": 5.00},
    "claude-sonnet-4-6":              {"in": 3.00,  "out": 15.00},
    "claude-opus-4-7":                {"in": 15.00, "out": 75.00},
    # Google via OpenRouter
    "google/gemini-2.0-flash-001":    {"in": 0.10,  "out": 0.40},
    "google/gemini-2.5-flash":        {"in": 0.15,  "out": 0.60},
    "google/gemini-2.5-pro":          {"in": 1.25,  "out": 10.00},
    "google/gemini-1.5-pro":          {"in": 1.25,  "out": 5.00},
    # OpenAI via OpenRouter
    "openai/gpt-4o":                  {"in": 2.50,  "out": 10.00},
    "openai/gpt-4o-mini":             {"in": 0.15,  "out": 0.60},
    # Meta via OpenRouter
    "meta-llama/llama-3.1-8b-instruct":  {"in": 0.06, "out": 0.06},
    "meta-llama/llama-3.1-70b-instruct": {"in": 0.35, "out": 0.40},
}

_DEFAULT_COST = {"in": 1.00, "out": 3.00}


def _calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    prices = _COST_TABLE.get(model, _DEFAULT_COST)
    return (tokens_in * prices["in"] + tokens_out * prices["out"]) / 1_000_000


# ---------------------------------------------------------------------------
# Tipos compartilhados
# ---------------------------------------------------------------------------


class LLMResponse(BaseModel):
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


# ---------------------------------------------------------------------------
# Logging de treino (compartilhado entre clientes)
# ---------------------------------------------------------------------------


def _log_training(
    conn: sqlite3.Connection,
    task: str,
    prompt: str,
    completion: str,
    model: str,
    system_prompt: str | None,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> None:
    from canal_soberania.db import log_training_example

    try:
        with conn:
            log_training_example(
                conn=conn,
                task=task,
                prompt=prompt,
                completion=completion,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                system_prompt=system_prompt,
            )
    except Exception as exc:
        logger.warning("training log falhou (não crítico): {}", exc)


# ---------------------------------------------------------------------------
# Cliente Anthropic (direto)
# ---------------------------------------------------------------------------


class LLMClient:
    def __init__(
        self,
        api_key: str,
        training_conn: sqlite3.Connection | None = None,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._training_conn = training_conn

    @retry(  # type: ignore[untyped-decorator]
        retry=retry_if_exception_type((
            anthropic.RateLimitError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            anthropic.InternalServerError,
        )),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        system: str | None = None,
        task: str = "",
    ) -> LLMResponse:
        messages: list[anthropic.types.MessageParam] = [{"role": "user", "content": prompt}]
        logger.debug("LLM call | model={} | task={} | prompt_len={}", model, task, len(prompt))

        if system:
            msg = self._client.messages.create(
                model=model, max_tokens=max_tokens, messages=messages, system=system
            )
        else:
            msg = self._client.messages.create(
                model=model, max_tokens=max_tokens, messages=messages
            )

        text_blocks = [b for b in msg.content if isinstance(b, anthropic.types.TextBlock)]
        text = text_blocks[0].text if text_blocks else ""
        tokens_in = msg.usage.input_tokens
        tokens_out = msg.usage.output_tokens
        cost = _calc_cost(model, tokens_in, tokens_out)

        logger.debug(
            "LLM done | model={} | in={} out={} cost=${:.5f}", model, tokens_in, tokens_out, cost
        )

        if self._training_conn is not None and task:
            _log_training(self._training_conn, task, prompt, text, model, system, tokens_in, tokens_out, cost)

        return LLMResponse(text=text, model=model, tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)


# ---------------------------------------------------------------------------
# Cliente OpenRouter (todos os demais modelos)
# ---------------------------------------------------------------------------


def _is_retriable_http_error(exc: BaseException) -> bool:
    return isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 500, 502, 503, 504)


class OpenRouterClient:
    _OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        training_conn: sqlite3.Connection | None = None,
    ) -> None:
        self._api_key = api_key
        self._training_conn = training_conn

    @retry(  # type: ignore[untyped-decorator]
        retry=(
            retry_if_exception_type((urllib.error.URLError, socket.timeout, json.JSONDecodeError))
            | retry_if_exception(_is_retriable_http_error)
        ),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _call_api(self, req: urllib.request.Request) -> dict[str, object]:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return dict(json.loads(resp.read()))  # type: ignore[arg-type]

    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        system: str | None = None,
        task: str = "",
    ) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        logger.debug("OpenRouter call | model={} | task={} | prompt_len={}", model, task, len(prompt))

        payload = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens}).encode()
        req = urllib.request.Request(
            self._OPENROUTER_URL,
            data=payload,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )

        data = self._call_api(req)

        text = data["choices"][0]["message"]["content"]  # type: ignore[index]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        cost = _calc_cost(model, tokens_in, tokens_out)

        logger.debug(
            "OpenRouter done | model={} | in={} out={} cost=${:.5f}", model, tokens_in, tokens_out, cost
        )

        if self._training_conn is not None and task:
            _log_training(self._training_conn, task, prompt, text, model, system, tokens_in, tokens_out, cost)

        return LLMResponse(text=text, model=model, tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)


# ---------------------------------------------------------------------------
# Factory: escolhe o cliente certo pelo nome do modelo
# ---------------------------------------------------------------------------


def get_llm_client(
    model: str,
    settings: object,
    training_conn: sqlite3.Connection | None = None,
) -> LLMClient | OpenRouterClient:
    """
    Retorna LLMClient (Anthropic direto) para modelos claude-*,
    OpenRouterClient para todos os demais.
    """
    from canal_soberania.config import Settings  # evita import circular no topo

    s: Settings = settings  # type: ignore[assignment]

    if model.startswith("claude-"):
        return LLMClient(api_key=s.anthropic_api_key, training_conn=training_conn)
    return OpenRouterClient(api_key=s.openrouter_api_key, training_conn=training_conn)


# ---------------------------------------------------------------------------
# Utilitário de extração de JSON
# ---------------------------------------------------------------------------


def extract_json(text: str) -> dict[str, object]:
    """Extrai primeiro bloco JSON da resposta do LLM."""
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            return dict(json.loads(stripped))
        except json.JSONDecodeError:
            pass

    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return dict(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass

    match2 = re.search(r"\{.*\}", text, re.DOTALL)
    if match2:
        return dict(json.loads(match2.group()))

    raise ValueError(f"Nenhum JSON encontrado na resposta: {text[:200]!r}")
