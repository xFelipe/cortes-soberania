"""Wrapper Anthropic API com retry, tracking de custo e coleta de dados de treino."""

from __future__ import annotations

import json
import re
import sqlite3

import anthropic
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from canal_soberania.logger import logger

# Preços por milhão de tokens (USD) — atualizar se mudar
_COST_TABLE: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-opus-4-7": {"in": 15.00, "out": 75.00},
}


def _calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    prices = _COST_TABLE.get(model, {"in": 3.00, "out": 15.00})
    return (tokens_in * prices["in"] + tokens_out * prices["out"]) / 1_000_000


class LLMResponse(BaseModel):
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


class LLMClient:
    def __init__(
        self,
        api_key: str,
        training_conn: sqlite3.Connection | None = None,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._training_conn = training_conn

    @retry(  # type: ignore[untyped-decorator]
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APITimeoutError)),
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
        messages: list[anthropic.types.MessageParam] = [
            {"role": "user", "content": prompt}
        ]
        logger.debug("LLM call | model={} | task={} | prompt_len={}", model, task, len(prompt))
        if system:
            msg = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                system=system,
            )
        else:
            msg = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
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
            self._log_training(
                task=task,
                prompt=prompt,
                completion=text,
                model=model,
                system_prompt=system,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
            )

        return LLMResponse(
            text=text,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )

    def _log_training(
        self,
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
            with self._training_conn:  # type: ignore[union-attr]
                log_training_example(
                    conn=self._training_conn,  # type: ignore[arg-type]
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


def extract_json(text: str) -> dict[str, object]:
    """Extrai primeiro bloco JSON da resposta do LLM."""
    # Tenta direto primeiro
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            return dict(json.loads(stripped))
        except json.JSONDecodeError:
            pass

    # Busca bloco ```json ... ```
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return dict(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass

    # Busca qualquer { ... }
    match2 = re.search(r"\{.*\}", text, re.DOTALL)
    if match2:
        return dict(json.loads(match2.group()))

    raise ValueError(f"Nenhum JSON encontrado na resposta: {text[:200]!r}")
