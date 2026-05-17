"""Decorators de retry para chamadas de rede."""

from __future__ import annotations

from typing import Any, Type

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


def network_retry(
    exceptions: tuple[Type[BaseException], ...],
    attempts: int = 5,
    min_wait: int = 4,
    max_wait: int = 60,
) -> Any:
    """Decorator de retry com backoff exponencial para falhas de rede transitórias."""
    return retry(
        retry=retry_if_exception_type(exceptions),
        wait=wait_exponential(multiplier=2, min=min_wait, max=max_wait),
        stop=stop_after_attempt(attempts),
        reraise=True,
    )
