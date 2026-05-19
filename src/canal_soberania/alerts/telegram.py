"""Canal de alerta via Telegram Bot API."""

from __future__ import annotations

import urllib.parse
import urllib.request

from canal_soberania.logger import logger

_HTTP_OK = 200

_LEVEL_EMOJI = {
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "🚨",
    "critical": "🔴",
}


class TelegramChannel:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    @property
    def configured(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def send(self, title: str, body: str, level: str = "warning") -> bool:
        if not self.configured:
            logger.debug("Telegram não configurado — alerta ignorado")
            return False

        emoji = _LEVEL_EMOJI.get(level, "⚠️")
        message = f"{emoji} *{title}*\n{body}"
        return self._post(message)

    def _post(self, message: str) -> bool:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            data = (
                f"chat_id={urllib.parse.quote(self._chat_id)}"
                f"&text={urllib.parse.quote(message)}"
                f"&parse_mode=Markdown"
            ).encode()
            req = urllib.request.Request(url, data=data, method="POST")  # noqa: S310
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                ok: bool = resp.status == _HTTP_OK
                if ok:
                    logger.debug("Telegram: alerta enviado com sucesso")
                return ok
        except Exception as exc:
            logger.warning("Telegram: falha ao enviar alerta: {}", exc)
            return False
