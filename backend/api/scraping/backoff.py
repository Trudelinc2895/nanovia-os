from __future__ import annotations

import random

from api.config import settings


def exponential_backoff_seconds(attempt: int, *, jitter: bool = True) -> float:
    if attempt <= 0:
        raise ValueError("attempt must be >= 1")

    base = settings.SCRAPING_RETRY_BACKOFF_BASE_MS / 1000.0
    delay = base * (2 ** (attempt - 1))
    if not jitter:
        return delay
    return delay + random.uniform(0, delay / 2)

