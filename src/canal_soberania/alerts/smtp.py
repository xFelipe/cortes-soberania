"""Canal de alerta via SMTP (email)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from canal_soberania.logger import logger

_LEVEL_PREFIX = {
    "info": "[INFO]",
    "warning": "[AVISO]",
    "error": "[ERRO]",
    "critical": "[CRÍTICO]",
}


class SmtpChannel:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: str,
        to_addr: str,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = from_addr
        self._to = to_addr

    @property
    def configured(self) -> bool:
        return bool(self._host and self._to)

    def send(self, title: str, body: str, level: str = "warning") -> bool:
        if not self.configured:
            logger.debug("SMTP não configurado — alerta ignorado")
            return False

        prefix = _LEVEL_PREFIX.get(level, "[AVISO]")
        subject = f"{prefix} Canal Soberania — {title}"
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self._from or self._user
            msg["To"] = self._to
            msg.set_content(body)

            with smtplib.SMTP(self._host, self._port, timeout=15) as server:
                server.ehlo()
                if server.has_extn("starttls"):
                    server.starttls()
                    server.ehlo()
                if self._user and self._password:
                    server.login(self._user, self._password)
                server.send_message(msg)

            logger.debug("SMTP: alerta enviado para {}", self._to)
            return True
        except Exception as exc:
            logger.warning("SMTP: falha ao enviar alerta: {}", exc)
            return False
