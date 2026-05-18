"""Alertas de operação — verifica itens presos e notifica via Telegram."""

from __future__ import annotations

import sqlite3
import urllib.request

from canal_soberania.db import status_summary
from canal_soberania.logger import logger

_STUCK_THRESHOLD = 50


def _send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    """Envia mensagem via Telegram Bot API. Retorna True se bem-sucedido."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = f"chat_id={chat_id}&text={urllib.parse.quote(message)}&parse_mode=Markdown".encode()
    try:
        import urllib.parse

        data = f"chat_id={urllib.parse.quote(chat_id)}&text={urllib.parse.quote(message)}&parse_mode=Markdown".encode()
        req = urllib.request.Request(url, data=data, method="POST")  # noqa: S310
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return resp.status == 200
    except Exception as exc:
        logger.warning("Telegram: falha ao enviar alerta: {}", exc)
        return False


def check_stuck(
    conn: sqlite3.Connection,
    threshold: int = _STUCK_THRESHOLD,
    bot_token: str = "",
    chat_id: str = "",
) -> list[tuple[str, int]]:
    """
    Verifica se algum status tem mais que `threshold` itens.
    Se Telegram configurado, envia alerta para cada status crítico.
    Retorna lista de (status, count) que estão acima do threshold.
    """
    summary = status_summary(conn)
    stuck = [(status, count) for status, count in summary.items() if count > threshold]

    if not stuck:
        logger.debug("check_stuck: nenhum status acima de {}", threshold)
        return []

    for status, count in stuck:
        logger.warning("ALERTA: {} itens presos em status '{}'", count, status)

    if bot_token and chat_id:
        lines = [f"*Canal Soberania — Alerta de Pipeline*"]
        lines.append(f"Itens presos (threshold={threshold}):")
        for status, count in stuck:
            lines.append(f"  • `{status}`: {count} itens")
        message = "\n".join(lines)
        ok = _send_telegram(bot_token, chat_id, message)
        if ok:
            logger.info("Alerta Telegram enviado ({} status críticos)", len(stuck))
        else:
            logger.warning("Falha ao enviar alerta Telegram")

    return stuck
