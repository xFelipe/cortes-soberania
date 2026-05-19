"""Protocolo base para canais de alerta."""

from __future__ import annotations

from typing import Protocol


class AlertChannel(Protocol):
    def send(self, title: str, body: str, level: str = "warning") -> bool:
        """Envia alerta. Retorna True se bem-sucedido."""
        ...
