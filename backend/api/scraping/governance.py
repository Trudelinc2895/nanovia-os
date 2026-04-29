"""backend/api/scraping/governance.py — Per-API-key budget enforcement and anomaly detection."""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


async def enforce_api_key_budget(api_key_hash: str, store) -> None:
    """Enforce hourly and daily budget limits for an API key.

    Uses Redis INCR + EXPIRE for window counting.  Both limits are disabled
    when set to 0 (default).

    Args:
        api_key_hash: Hashed API key identifier.
        store:        Module providing ``incr_with_ttl(key, ttl) -> int``.
    """
    from api.config import settings
    from fastapi import HTTPException

    hourly = settings.SCRAPING_API_KEY_HOURLY_BUDGET
    daily = settings.SCRAPING_API_KEY_DAILY_BUDGET

    if hourly <= 0 and daily <= 0:
        return

    now = int(time.time())

    if hourly > 0:
        hour_bucket = now // 3600
        key_h = f"scrape:budget:hourly:{api_key_hash}:{hour_bucket}"
        count_h = await store.incr_with_ttl(key_h, 3600)
        if count_h > hourly:
            raise HTTPException(status_code=429, detail="API key hourly budget exceeded")

    if daily > 0:
        day_bucket = now // 86400
        key_d = f"scrape:budget:daily:{api_key_hash}:{day_bucket}"
        count_d = await store.incr_with_ttl(key_d, 86400)
        if count_d > daily:
            raise HTTPException(status_code=429, detail="API key daily budget exceeded")


def detect_anomaly(client_id: str, current_rate: int, baseline_rate: int) -> bool:
    """Detect a traffic spike for a client.

    Returns True when current_rate exceeds baseline_rate multiplied by the
    configured SCRAPING_ANOMALY_BASELINE_MULTIPLIER.  Always returns False when
    baseline_rate ≤ 0 (no baseline established yet).

    Args:
        client_id:     Identifier for logging context.
        current_rate:  Observed request rate in the current window.
        baseline_rate: Historical baseline rate.
    """
    from api.config import settings

    if baseline_rate <= 0:
        return False
    multiplier = settings.SCRAPING_ANOMALY_BASELINE_MULTIPLIER
    result = current_rate > baseline_rate * multiplier
    if result:
        logger.warning(
            "anomaly_detected client=%s current_rate=%d baseline=%d multiplier=%.1f",
            client_id,
            current_rate,
            baseline_rate,
            multiplier,
        )
    return result
