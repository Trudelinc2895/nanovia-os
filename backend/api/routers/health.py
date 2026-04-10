"""backend/api/routers/health.py — Liveness + readiness health checks."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health():
    """
    Liveness probe — always returns 200 if the process is alive.
    Used by Caddy, Docker healthchecks, and uptime monitors.
    """
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/health/ready")
async def readiness():
    """
    Readiness probe — checks DB and Redis connectivity.
    Returns 200 only when all dependencies are reachable.
    Used by deploy pipeline to confirm the new container is ready before marking deploy as successful.
    """
    from api.database import get_db

    checks: dict[str, str] = {}
    healthy = True

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    try:
        async for db in get_db():
            await db.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
            break
    except Exception as exc:
        logger.error("[health/ready] postgres check failed: %s", exc)
        checks["postgres"] = f"error: {type(exc).__name__}"
        healthy = False

    # ── Redis ──────────────────────────────────────────────────────────────────
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.error("[health/ready] redis check failed: %s", exc)
        checks["redis"] = f"error: {type(exc).__name__}"
        healthy = False

    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if healthy else "degraded",
            "checks": checks,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/")
async def root():
    return {"message": f"{settings.APP_NAME} — online"}
