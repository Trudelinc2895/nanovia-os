"""
backend/api/main.py
KT Monetization OS — FastAPI production entry point
"""
from __future__ import annotations
import base64 as _base64
import json as _json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as _aioredis
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
load_dotenv(".env")

from api.config import settings
from api.database import engine, Base
from api.routers import auth, billing, modules, users, health, mobile, orchestrate, ghost_agency, content_cloner, analytics
from api.routers import notifications
from api.routers import admin
from api.routers import team
# Import models so Base knows about them before create_all
import api.models  # noqa: F401

from api.core.logging import setup_logging, set_request_id
setup_logging(level=settings.LOG_LEVEL if hasattr(settings, "LOG_LEVEL") else "INFO")

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    print(f"[startup] {settings.APP_NAME} v{settings.APP_VERSION} env={settings.APP_ENV}")
    # Auto-create tables (idempotent — use Alembic for schema changes in prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[startup] DB tables ready")
    yield
    print("[shutdown] clean exit")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_meta(request: Request, call_next) -> Response:
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    set_request_id(req_id)
    start = time.perf_counter()
    response: Response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Response-Time"] = f"{ms:.1f}ms"
    return response


# ─── Redis rate limiting ───────────────────────────────────────────────────────

_redis_pool: _aioredis.Redis | None = None


async def _get_redis() -> _aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = _aioredis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
    return _redis_pool


def _extract_sub(authorization: str | None) -> str | None:
    """Decode JWT payload (no signature check) to extract the sub claim."""
    try:
        if not authorization or not authorization.startswith("Bearer "):
            return None
        token = authorization.split(" ", 1)[1]
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = _json.loads(_base64.urlsafe_b64decode(payload_b64))
        return str(payload["sub"])
    except Exception:
        return None


_RATE_SKIP_PREFIXES = ("/health", "/metrics", "/docs", "/openapi.json", "/redoc")
_AUTH_RATE_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
}

# Stricter limits for 2FA — prevents TOTP brute force (6-digit = 1M combos)
_STRICT_RATE_PATHS = {
    "/api/v1/auth/2fa/verify-login",
    "/api/v1/auth/2fa/enable",
    "/api/v1/auth/2fa/disable",
}


@app.middleware("http")
async def rate_limit(request: Request, call_next) -> Response:
    path = request.url.path
    if any(path.startswith(p) for p in _RATE_SKIP_PREFIXES):
        return await call_next(request)

    ip = (request.client.host if request.client else "unknown").replace(":", "_")

    if path in _STRICT_RATE_PATHS:
        # 5 attempts per 15 min per IP — brute force TOTP protection
        key = f"ratelimit:ip:{ip}:2fa"
        limit = 5
        try:
            redis = await _get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 900)  # 15 minutes
            if count > limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Trop de tentatives. Réessaie dans 15 minutes."},
                )
        except Exception:
            pass  # Redis unavailable — fail open
        return await call_next(request)
    elif path in _AUTH_RATE_PATHS:
        key = f"ratelimit:ip:{ip}:auth"
        limit = 10
    else:
        user_id = _extract_sub(request.headers.get("authorization"))
        if user_id:
            key = f"ratelimit:user:{user_id}"
            limit = 100
        else:
            key = f"ratelimit:ip:{ip}"
            limit = 30

    try:
        redis = await _get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Réessaie dans 60 secondes."},
            )
    except Exception:
        pass  # Redis unavailable — fail open

    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


if HAS_PROMETHEUS:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])
app.include_router(modules.router, prefix="/api/v1/modules", tags=["modules"])
app.include_router(mobile.router, prefix="/api/v1", tags=["mobile"])
app.include_router(orchestrate.router, prefix="/api/v1", tags=["AI orchestrator"])
app.include_router(content_cloner.router, prefix="/api/v1", tags=["content cloner"])
app.include_router(ghost_agency.router, prefix="/api/v1", tags=["ghost agency"])
app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"])
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(team.router, prefix="/api/v1", tags=["team"])
from api.routers.contact import router as contact_router
app.include_router(contact_router, prefix="/api/v1", tags=["contact"])
