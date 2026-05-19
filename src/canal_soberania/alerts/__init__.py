"""Alertas operacionais — Telegram, SMTP e roteador configurável via env."""

from canal_soberania.alerts.router import AlertRouter
from canal_soberania.alerts.smtp import SmtpChannel
from canal_soberania.alerts.telegram import TelegramChannel

__all__ = ["AlertRouter", "SmtpChannel", "TelegramChannel"]
