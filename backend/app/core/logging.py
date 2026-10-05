"""Structured JSON logging with request-id correlation."""
from __future__ import annotations

import contextvars
import logging
import sys

from pythonjsonlogger.json import JsonFormatter

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

SENSITIVE_KEYS = ("password", "token", "secret", "authorization", "api_key", "cookie")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s"))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s"))
    handler.addFilter(_ContextFilter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def redact(d: dict) -> dict:
    return {k: ("***" if any(s in k.lower() for s in SENSITIVE_KEYS) else v) for k, v in d.items()}
