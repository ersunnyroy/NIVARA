"""Pluggable notification channels. Add a channel by subclassing Notifier and registering it."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config.settings import get_settings

log = logging.getLogger(__name__)


class Notifier:
    name = "base"

    def available(self) -> bool:
        return True

    def send(self, to: str | None, title: str, message: str, data: dict) -> str:
        raise NotImplementedError


class InAppNotifier(Notifier):
    name = "in_app"

    def send(self, to, title, message, data) -> str:
        return "stored"  # the AlertEvent row itself is the in-app notification


class EmailNotifier(Notifier):
    name = "email"

    def available(self) -> bool:
        s = get_settings()
        return bool(s.smtp_host and s.smtp_from)

    def send(self, to, title, message, data) -> str:
        s = get_settings()
        if not (self.available() and to):
            return "skipped: SMTP not configured"
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = f"[NIVARA] {title}", s.smtp_from, to
        msg.set_content(message + "\n\nResearch alert only — not investment advice.")
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
        return "sent"


class WebhookNotifier(Notifier):
    name = "webhook"

    def available(self) -> bool:
        return bool(get_settings().alert_webhook_url)

    def send(self, to, title, message, data) -> str:
        url = get_settings().alert_webhook_url
        if not url:
            return "skipped: ALERT_WEBHOOK_URL not configured"
        r = httpx.post(url, json={"title": title, "message": message, "data": data}, timeout=10)
        return f"http {r.status_code}"


REGISTRY: dict[str, Notifier] = {n.name: n for n in (InAppNotifier(), EmailNotifier(), WebhookNotifier())}


def dispatch(channels: list[str], to: str | None, title: str, message: str, data: dict) -> dict:
    out = {}
    for ch in channels or ["in_app"]:
        n = REGISTRY.get(ch)
        if n is None:
            out[ch] = "unknown channel"
            continue
        try:
            out[ch] = n.send(to, title, message, data)
        except Exception as e:
            log.warning("notifier %s failed: %s", ch, e)
            out[ch] = f"error: {type(e).__name__}"
    return out
