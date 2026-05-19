"""Roteador de alertas — distribui para todos os canais configurados."""

from __future__ import annotations

from canal_soberania.alerts.base import AlertChannel
from canal_soberania.logger import logger


class AlertRouter:
    """Agrega múltiplos AlertChannels e envia para todos de uma vez."""

    def __init__(self, channels: list[AlertChannel]) -> None:
        self._channels = channels

    @classmethod
    def from_settings(cls, settings: object) -> "AlertRouter":
        """Constrói roteador a partir das settings da aplicação."""
        from canal_soberania.alerts.smtp import SmtpChannel
        from canal_soberania.alerts.telegram import TelegramChannel
        from canal_soberania.config import Settings

        s: Settings = settings  # type: ignore[assignment]
        channels: list[AlertChannel] = []

        alert_channels = {c.strip() for c in s.alert_channels.split(",") if c.strip()}

        if "telegram" in alert_channels or not alert_channels:
            ch = TelegramChannel(s.telegram_bot_token, s.telegram_chat_id)
            if ch.configured:
                channels.append(ch)

        if "smtp" in alert_channels:
            ch_smtp = SmtpChannel(
                host=s.smtp_host,
                port=s.smtp_port,
                user=s.smtp_user,
                password=s.smtp_password,
                from_addr=s.smtp_from,
                to_addr=s.smtp_to,
            )
            if ch_smtp.configured:
                channels.append(ch_smtp)

        return cls(channels)

    def send(self, title: str, body: str, level: str = "warning") -> int:
        """Envia alerta para todos os canais. Retorna número de envios bem-sucedidos."""
        if not self._channels:
            logger.debug("AlertRouter: nenhum canal configurado")
            return 0

        success = sum(1 for ch in self._channels if ch.send(title, body, level))
        logger.info("AlertRouter: {}/{} canais notificados", success, len(self._channels))
        return success

    def send_pipeline_stuck(self, stuck_items: list[tuple[str, int]]) -> int:
        lines = ["Itens presos no pipeline:"]
        for status, count in stuck_items:
            lines.append(f"  • {status}: {count}")
        return self.send(
            title="Pipeline com itens presos",
            body="\n".join(lines),
            level="warning",
        )

    def send_pipeline_stopped(self, hours: float) -> int:
        return self.send(
            title="Pipeline parado",
            body=f"Nenhuma iteração do loop há {hours:.1f}h. Verifique o processo.",
            level="error",
        )

    def send_health_ok(self, summary: str) -> int:
        return self.send(
            title="Healthcheck OK",
            body=summary,
            level="info",
        )
