"""backend/api/middleware/pii.py — PII log anonymization filter."""
from __future__ import annotations

import logging
import re

# Email: user@example.com → u***@e***.com
_EMAIL_RE = re.compile(
    r"\b([A-Za-z0-9])[A-Za-z0-9._%+\-]*@([A-Za-z0-9])[A-Za-z0-9.\-]*\.([A-Za-z]{2,})\b"
)
# IPv4: 192.168.1.100 → 192.168.1.***
_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}\b")
# JWT Bearer token: Bearer eyJxxx.yyy.zzz → Bearer eyJxxx.yyy.[REDACTED]
_JWT_RE = re.compile(
    r"(Bearer\s+eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)\.[A-Za-z0-9_\-]+"
)


def _mask(text: str) -> str:
    """Apply all PII masks to *text*."""
    text = _EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}***.{m.group(3)}", text)
    text = _IP_RE.sub(lambda m: f"{m.group(1)}.***", text)
    text = _JWT_RE.sub(r"\1.[REDACTED]", text)
    return text


class PIIFilter(logging.Filter):
    """logging.Filter that redacts emails, IPs, and JWTs from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _mask(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    _mask(a) if isinstance(a, str) else a for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: (_mask(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
        return True
