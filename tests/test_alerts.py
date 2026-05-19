"""Testes para o pacote alerts/ (Telegram, SMTP, AlertRouter)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from canal_soberania.alerts.router import AlertRouter
from canal_soberania.alerts.smtp import SmtpChannel
from canal_soberania.alerts.telegram import TelegramChannel


class TestTelegramChannel:
    def test_not_configured_when_empty(self) -> None:
        ch = TelegramChannel("", "")
        assert not ch.configured

    def test_configured_when_both_set(self) -> None:
        ch = TelegramChannel("token123", "chat456")
        assert ch.configured

    def test_send_returns_false_when_not_configured(self) -> None:
        ch = TelegramChannel("", "")
        assert ch.send("title", "body") is False

    def test_send_success(self) -> None:
        ch = TelegramChannel("token", "chat")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = ch.send("Título", "Mensagem", level="error")

        assert result is True

    def test_send_returns_false_on_network_error(self) -> None:
        ch = TelegramChannel("token", "chat")
        with patch("urllib.request.urlopen", side_effect=OSError("network")):
            result = ch.send("Título", "Mensagem")
        assert result is False


class TestSmtpChannel:
    def test_not_configured_when_no_host(self) -> None:
        ch = SmtpChannel("", 587, "", "", "", "dest@mail.com")
        assert not ch.configured

    def test_not_configured_when_no_to(self) -> None:
        ch = SmtpChannel("smtp.host.com", 587, "", "", "", "")
        assert not ch.configured

    def test_configured_when_host_and_to_set(self) -> None:
        ch = SmtpChannel("smtp.host.com", 587, "u", "p", "from@m.com", "to@m.com")
        assert ch.configured

    def test_send_returns_false_when_not_configured(self) -> None:
        ch = SmtpChannel("", 587, "", "", "", "")
        assert ch.send("t", "b") is False

    def test_send_uses_starttls(self) -> None:
        ch = SmtpChannel("smtp.host.com", 587, "user", "pass", "f@m.com", "t@m.com")
        mock_server = MagicMock()
        mock_server.__enter__ = lambda s: mock_server
        mock_server.__exit__ = MagicMock(return_value=False)
        mock_server.has_extn.return_value = True

        with patch("smtplib.SMTP", return_value=mock_server):
            result = ch.send("Título", "Corpo")

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.send_message.assert_called_once()

    def test_send_returns_false_on_smtp_error(self) -> None:
        ch = SmtpChannel("smtp.host.com", 587, "u", "p", "f@m.com", "t@m.com")
        with patch("smtplib.SMTP", side_effect=OSError("conn refused")):
            result = ch.send("Título", "Corpo")
        assert result is False


class TestAlertRouter:
    def test_empty_router_sends_zero(self) -> None:
        router = AlertRouter([])
        assert router.send("t", "b") == 0

    def test_routes_to_all_channels(self) -> None:
        ch1 = MagicMock()
        ch1.send.return_value = True
        ch2 = MagicMock()
        ch2.send.return_value = True
        router = AlertRouter([ch1, ch2])  # type: ignore[list-item]
        assert router.send("Título", "Corpo") == 2
        ch1.send.assert_called_once_with("Título", "Corpo", "warning")
        ch2.send.assert_called_once_with("Título", "Corpo", "warning")

    def test_counts_only_successes(self) -> None:
        ch1 = MagicMock()
        ch1.send.return_value = True
        ch2 = MagicMock()
        ch2.send.return_value = False
        router = AlertRouter([ch1, ch2])  # type: ignore[list-item]
        assert router.send("t", "b") == 1

    def test_send_pipeline_stuck(self) -> None:
        ch = MagicMock()
        ch.send.return_value = True
        router = AlertRouter([ch])  # type: ignore[list-item]
        router.send_pipeline_stuck([("downloading", 5), ("transcribing", 3)])
        ch.send.assert_called_once()
        title, body, *_ = ch.send.call_args.args
        assert "Pipeline" in title
        assert "downloading" in body

    def test_from_settings_no_channels_when_not_configured(self) -> None:
        from canal_soberania.config import Settings
        s = Settings(telegram_bot_token="", telegram_chat_id="", alert_channels="telegram")
        router = AlertRouter.from_settings(s)
        assert router.send("t", "b") == 0

    def test_from_settings_telegram_when_configured(self) -> None:
        from canal_soberania.config import Settings
        s = Settings(
            telegram_bot_token="tok",
            telegram_chat_id="cid",
            alert_channels="telegram",
        )
        router = AlertRouter.from_settings(s)
        assert len(router._channels) == 1
        assert isinstance(router._channels[0], TelegramChannel)
