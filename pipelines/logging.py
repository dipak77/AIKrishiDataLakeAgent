"""Structured JSON logging + correlation ids (Track 10 observability).

Every log record is a single JSON line so lake jobs can be parsed by
log-shippers without regex. A `correlation_id` (contextvar) tags all records
emitted while handling one run/request, so a connector failure can be traced
across the seed → gold → validate chain.

Use `get_json_logger(__name__)` as a drop-in replacement for
`logging.getLogger(__name__)`.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import uuid
from typing import Any

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "agrilake_correlation_id", default=""
)

_EPOCH = time.time()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": round(time.time() - _EPOCH, 3),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": _correlation_id.get() or None,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extras = getattr(record, "extras", None)
        if isinstance(extras, dict):
            payload.update(extras)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    # Replace existing stream handlers to avoid duplicate lines.
    for existing in list(root.handlers):
        if isinstance(existing, logging.StreamHandler):
            root.removeHandler(existing)
    root.addHandler(handler)


def get_json_logger(name: str) -> logging.Logger:
    """Return a logger that emits structured JSON via the root handler."""
    return logging.getLogger(name)


def new_correlation_id() -> str:
    """Generate and set a fresh correlation id for the current context."""
    cid = uuid.uuid4().hex[:12]
    _correlation_id.set(cid)
    return cid


def current_correlation_id() -> str:
    return _correlation_id.get()


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit a single structured event (message=event + arbitrary fields)."""
    logger.info(event, extra={"extras": fields})
