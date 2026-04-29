"""backend/api/routers/chaos.py — Admin-only chaos engineering endpoint.

IMPORTANT: This router is only registered when CHAOS_ENABLED=true.
           It MUST NOT be enabled in production.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

ChaosTarget = Literal["redis_fail", "worker_kill", "queue_flood", "slow_response"]

_VALID_TARGETS: frozenset[str] = frozenset(
    {"redis_fail", "worker_kill", "queue_flood", "slow_response"}
)


async def _require_chaos_and_admin():
    """Guard: chaos must be enabled and we must NOT be in production."""
    if not settings.CHAOS_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    if settings.APP_ENV == "production":
        raise HTTPException(
            status_code=503,
            detail="Chaos injection is disabled in production",
        )


@router.get("/api/v1/chaos/inject/{target}")
async def inject_chaos(
    target: str,
    _guard: None = Depends(_require_chaos_and_admin),
) -> JSONResponse:
    """Inject a controlled fault into the running system.

    Available targets:
    - ``redis_fail``    — Write a poison key that causes Redis ops to fail for 10 s.
    - ``queue_flood``   — Enqueue 100 fake job IDs to simulate queue saturation.
    - ``slow_response`` — Sleep 25 s to test upstream timeout handling.
    - ``worker_kill``   — Raise CancelledError to kill an in-process worker task.
    """
    if target not in _VALID_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown target {target!r}. Valid: {sorted(_VALID_TARGETS)}",
        )

    logger.warning("chaos_inject target=%s env=%s", target, settings.APP_ENV)

    if target == "redis_fail":
        try:
            from api.scraping.store import get_redis
            redis = await get_redis()
            await redis.set("chaos:poison", "1", ex=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("chaos redis_fail setup error: %s", exc)
        return JSONResponse(
            {"injected": target, "duration_seconds": 10, "note": "staging only"}
        )

    if target == "queue_flood":
        try:
            from api.scraping.store import enqueue_job
            for i in range(100):
                await enqueue_job(f"chaos-fake-job-{i:04d}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("chaos queue_flood error: %s", exc)
        return JSONResponse(
            {"injected": target, "duration_seconds": 0, "note": "staging only", "jobs_enqueued": 100}
        )

    if target == "slow_response":
        await asyncio.sleep(25)
        return JSONResponse(
            {"injected": target, "duration_seconds": 25, "note": "staging only"}
        )

    if target == "worker_kill":
        raise asyncio.CancelledError("chaos worker_kill")

    # Unreachable — guarded above
    raise HTTPException(status_code=400, detail="Unknown target")
