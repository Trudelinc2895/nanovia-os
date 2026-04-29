"""backend/api/core/logging.py — Structured logging configuration.

Sets up JSON-compatible logging with correlation IDs for production traceability.
Each log record includes: timestamp, level, logger, message, traceId, region,
service name, and request context.
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

# Thread-local request context
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_user_id_var: ContextVar[str] = ContextVar("user_id", default="")


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(value: str) -> None:
    _request_id_var.set(value)


def get_user_id() -> str:
    return _user_id_var.get()


def set_user_id(value: str) -> None:
    _user_id_var.set(value)


class ContextFilter(logging.Filter):
    """Inject request_id and user_id into every log record."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.user_id = get_user_id() or "-"
        return True


class StructuredFormatter(logging.Formatter):
    """Emit every log record as a single-line JSON object.

    If ``record.msg`` is a dict (as emitted by ``_log_scrape_event``), its
    keys are merged into the top-level JSON object.
    """

    def format(self, record: logging.LogRecord) -> str:
        from api.config import settings as _s  # local import to avoid circular

        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        trace_id = get_request_id() or "-"
        user_id = get_user_id() or "-"

        payload: dict = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "service": "api",
            "region": getattr(_s, "APP_REGION", "local"),
            "traceId": trace_id,
            "userId": user_id,
        }

        if isinstance(record.msg, dict):
            payload.update(record.msg)
            payload.setdefault("msg", "")
        else:
            try:
                msg = record.getMessage()
            except Exception:
                msg = str(record.msg)
            payload["msg"] = msg

        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with structured JSON format, context filter, and PII masking."""
    from api.middleware.pii import PIIFilter

    formatter = StructuredFormatter()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.addFilter(PIIFilter())
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Apply same handler to uvicorn.access
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.addHandler(handler)
    uvicorn_access.propagate = False

    # Quiet noisy libraries
    for quiet in ("sqlalchemy.engine", "stripe", "httpx"):
        logging.getLogger(quiet).setLevel(logging.WARNING)

