"""Envio de e-mail (research.md R6): SMTP em dev/produção, memória nos testes.

Uma falha de envio nunca propaga: `send` devolve False e o chamador responde `emailSent: false`.
O log de falha não leva o conteúdo nem o link (o token é segredo).
"""

import logging
import smtplib
from email.message import EmailMessage
from html import escape
from typing import Protocol
from urllib.parse import quote

from sociman_api.config import Settings, get_settings

log = logging.getLogger(__name__)


class EmailSender(Protocol):
    def send(self, to: str, subject: str, text: str, html: str) -> bool: ...


class SmtpEmailSender:
    def __init__(self, settings: Settings):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.sender = settings.smtp_from
        self.timeout = settings.smtp_timeout

    def send(self, to: str, subject: str, text: str, html: str) -> bool:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            log.warning("falha ao enviar e-mail via %s:%s (%s)", self.host, self.port,
                        type(exc).__name__)
            return False
        return True


class MemoryEmailSender:
    """Guarda as mensagens em `outbox`. Com `fail = True`, simula falha de envio."""

    def __init__(self, fail: bool = False):
        self.outbox: list[dict] = []
        self.fail = fail

    def send(self, to: str, subject: str, text: str, html: str) -> bool:
        if self.fail:
            return False
        self.outbox.append({"to": to, "subject": subject, "text": text, "html": html})
        return True


def get_email_sender() -> EmailSender:
    return SmtpEmailSender(get_settings())


def _link(path: str, token: str) -> str:
    base = get_settings().app_url.rstrip("/")
    return f"{base}/{path}?token={quote(token, safe='')}"


def _render(subject: str, name: str, intro: str, action: str, link: str,
            outro: str) -> tuple[str, str, str]:
    text = f"Olá, {name}.\n\n{intro}\n\n{link}\n\n{outro}\n\nSociMan\n"
    html = (
        f"<p>Olá, {escape(name)}.</p>"
        f"<p>{escape(intro)}</p>"
        f'<p><a href="{escape(link)}">{escape(action)}</a></p>'
        f"<p>Se o botão não funcionar, copie este endereço: {escape(link)}</p>"
        f"<p>{escape(outro)}</p>"
        "<p>SociMan</p>"
    )
    return subject, text, html


def verification_email(name: str, token: str) -> tuple[str, str, str]:
    """Devolve (assunto, texto, html) do e-mail de confirmação."""
    return _render(
        "Confirme seu e-mail no SociMan",
        name,
        "Confirme seu e-mail para acessar o SociMan:",
        "Confirmar e-mail",
        _link("verify-email", token),
        f"O link vale por {get_settings().verify_ttl // 3600} horas. "
        "Se você não esperava este e-mail, ignore-o.",
    )


def reset_email(name: str, token: str) -> tuple[str, str, str]:
    """Devolve (assunto, texto, html) do e-mail de redefinição de senha."""
    return _render(
        "Redefinir sua senha do SociMan",
        name,
        "Recebemos um pedido para redefinir sua senha. Use o link abaixo:",
        "Redefinir senha",
        _link("reset-password", token),
        f"O link vale por {get_settings().reset_ttl // 60} minutos e só pode ser usado uma vez. "
        "Se você não pediu, ignore este e-mail.",
    )
