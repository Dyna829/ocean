"""Structured, leveled logging shared by the API.

Levels follow the standard library: DEBUG < INFO < WARNING < ERROR. The level is
selected with ``LOG_LEVEL`` (default INFO); set ``LOG_FORMAT=json`` for one JSON
object per line and ``LOG_SLOW_REQUEST_MS`` to choose the slow-request threshold.

Every record carries the current ``request_id`` so a request, its business events,
and its error trace can be correlated. Use ``extra={"fields": {...}}`` to attach
structured fields; never put secrets or full request bodies in them.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_LOGGER_WIDTH = 20
_configured = False


def _timestamp(record: logging.LogRecord) -> str:
    return (
        datetime.fromtimestamp(record.created, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    fields = getattr(record, "fields", None)
    return fields if isinstance(fields, dict) else {}


def _render(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return json.dumps(text, ensure_ascii=False) if any(c in text for c in ' "=\n') else text


class TextFormatter(logging.Formatter):
    """Human-readable single line: ts level logger event request_id key=value..."""

    def format(self, record: logging.LogRecord) -> str:
        parts = [
            _timestamp(record),
            f"{record.levelname:<7}",
            f"{record.name:<{_LOGGER_WIDTH}}",
            record.getMessage(),
            f"request_id={REQUEST_ID.get()}",
        ]
        for key, value in _fields(record).items():
            parts.append(f"{key}={_render(value)}")
        line = " ".join(parts)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class JsonFormatter(logging.Formatter):
    """One JSON object per line, suitable for log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": REQUEST_ID.get(),
            **_fields(record),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str = "app") -> logging.Logger:
    return logging.getLogger(name)


def configure_logging() -> None:
    """Configure the root logger once per process."""
    global _configured
    if _configured:
        return

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if not isinstance(level, int):
        level = logging.INFO

    use_json = os.environ.get("LOG_FORMAT", "text").strip().lower() == "json"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if use_json else TextFormatter())
    handler._cca_handler = True  # type: ignore[attr-defined]

    root = logging.getLogger()
    if not any(getattr(existing, "_cca_handler", False) for existing in root.handlers):
        root.addHandler(handler)
    root.setLevel(level)

    for noisy in ("httpx", "httpcore", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
