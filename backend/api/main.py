"""
backend/api/main.py
Nanovia OS — FastAPI production entry point
"""
from __future__ import annotations
import asyncio
import base64 as _base64
import json as _json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from urllib.parse import urlsplit, urlunsplit

if os.name == "nt" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
import redis.asyncio as _aioredis
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.config import settings
from api.database import engine, Base
from api.routers import auth, billing, modules, users, health, mobile, orchestrate, ghost_agency, content_cloner, analytics
from api.routers import micro_saas, decision_engine, knowledge_weapon, digital_leverage, reverse_engineering, offer_generator, execution_service
from api.routers import notifications
from api.routers import admin
from api.routers import admin_orchestrator
from api.routers import branding
from api.routers import custom_modules
from api.routers import team
from api.routers import scrape
from api.scraping.worker import run_worker_forever
from api.middleware.body_limit import BodySizeLimitMiddleware
# Import models so Base knows about them before create_all
import api.models  # noqa: F401

from api.core.logging import setup_logging, set_request_id
setup_logging(level=settings.LOG_LEVEL if hasattr(settings, "LOG_LEVEL") else "INFO")

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


_startup_logger = logging.getLogger("startup")
_NON_PROD_ENVS = {"development", "test"}


def _redact_connection_url(url: str) -> str:
    """Remove credentials from connection URLs before logging or surfacing them."""
    try:
        parsed = urlsplit(url)
    except Exception:
        return "<invalid-url>"

    if not parsed.scheme or not parsed.netloc:
        return url

    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""

    if parsed.username is None and parsed.password is None:
        netloc = parsed.netloc
    else:
        username = parsed.username or ""
        if parsed.password is not None:
            userinfo = f"{username}:***" if username else ":***"
        else:
            userinfo = username
        netloc = f"{userinfo}@{host}{port}" if userinfo else f"{host}{port}"

    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _validate_billing_startup_config() -> None:
    """Keep auth/API boot independent from partially configured Stripe catalogs."""
    _stripe_fields = {
        "STRIPE_PRICE_PRO_MONTHLY_ID": settings.STRIPE_PRICE_PRO_MONTHLY_ID,
        "STRIPE_PRICE_PRO_YEARLY_ID": settings.STRIPE_PRICE_PRO_YEARLY_ID,
        "STRIPE_PRICE_BUSINESS_MONTHLY_ID": settings.STRIPE_PRICE_BUSINESS_MONTHLY_ID,
        "STRIPE_PRICE_BUSINESS_YEARLY_ID": settings.STRIPE_PRICE_BUSINESS_YEARLY_ID,
    }
    _module_fields = {
        f"STRIPE_PRICE_MODULE_{m.upper()}": getattr(settings, f"STRIPE_PRICE_MODULE_{m.upper()}", "")
        for m in ["OPERATOR", "CONTENT", "MICRO_SAAS", "GHOST", "DECISION", "KNOWLEDGE", "LEVERAGE", "REVERSE", "OFFER", "EXECUTION"]
    }
    _missing_plan = [k for k, v in _stripe_fields.items() if not v]
    _missing_module = [k for k, v in _module_fields.items() if not v]

    if _missing_plan:
        if settings.APP_ENV == "production" and not any(_stripe_fields.values()):
            raise RuntimeError("FATAL: No Stripe plan price IDs configured in production.")
        _startup_logger.warning(
            "⚠️  Missing Stripe plan price IDs; affected checkouts will return 503: %s",
            _missing_plan,
        )
    if _missing_module:
        _startup_logger.info("ℹ️  Missing Stripe module price IDs (module checkout disabled): %s", _missing_module)


def _get_alembic_config() -> AlembicConfig:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_ini = os.path.join(project_root, "alembic.ini")
    config = AlembicConfig(alembic_ini)
    config.set_main_option("script_location", os.path.join(project_root, "alembic"))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


async def _ensure_expected_schema() -> None:
    """Fail fast outside development if the DB is not at Alembic head."""
    config = _get_alembic_config()
    expected_heads = set(ScriptDirectory.from_config(config).get_heads())
    if not expected_heads:
        raise RuntimeError("FATAL: No Alembic heads found. Migration setup is invalid.")

    async with engine.connect() as conn:
        try:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current_heads = {row[0] for row in result.fetchall()}
        except Exception as exc:
            raise RuntimeError(
                "FATAL: Database schema is not managed by Alembic. "
                "Bootstrap legacy prod DBs with 'python scripts/ensure_alembic_state.py' "
                "then run 'alembic upgrade head' before starting the API."
            ) from exc

    if current_heads != expected_heads:
        raise RuntimeError(
            "FATAL: Database schema is not at Alembic head. "
            f"expected={sorted(expected_heads)} current={sorted(current_heads)}. "
            "Run 'python scripts/ensure_alembic_state.py' if this is a legacy DB, "
            "then 'alembic upgrade head' before starting the API."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    scrape_worker_task: asyncio.Task | None = None
    print(f"[startup] {settings.APP_NAME} v{settings.APP_VERSION} env={settings.APP_ENV}")
    if settings.APP_ENV in _NON_PROD_ENVS:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[startup] DB tables ready (development create_all)")
    else:
        await _ensure_expected_schema()
        _startup_logger.info("[startup] DB schema validated at Alembic head")

    # ── Stripe price ID validation ──────────────────────────────────────────────
    _validate_billing_startup_config()

    # ── Redis health check ─────────────────────────────────────────────────────
    import logging as _log
    _redis_logger = _log.getLogger("startup")
    _safe_redis_url = _redact_connection_url(settings.REDIS_URL)
    try:
        _r = _aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        await _r.ping()
        await _r.aclose()
        _redis_logger.info("[startup] Redis ✅ connected at %s", _safe_redis_url)
    except Exception as _redis_exc:
        if settings.APP_ENV == "production":
            raise RuntimeError(
                f"FATAL: Redis unavailable in production ({_safe_redis_url}). "
                "Set REDIS_URL or provide a reachable Redis instance."
            ) from _redis_exc
        else:
            _redis_logger.warning(
                "⚠️  Redis not reachable (%s). Rate limiting will fail-open in dev. "
                "Requires Redis in production.",
                _redis_exc,
            )

    if settings.SCRAPING_ENABLED and settings.SCRAPING_RUN_WORKER_IN_API:
        scrape_worker_task = asyncio.create_task(run_worker_forever())
        _startup_logger.info("[startup] scrape worker task started in API process")

    yield

    if scrape_worker_task is not None:
        scrape_worker_task.cancel()
        try:
            await scrape_worker_task
        except asyncio.CancelledError:
            pass
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
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.API_BODY_SIZE_LIMIT_BYTES)


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
_RATE_LIMIT_RULES: dict[str, dict[str, object]] = {
    "/api/v1/auth/login": {"scope": "ip", "limit": 10, "window": 60, "bucket": "auth"},
    "/api/v1/auth/register": {"scope": "ip", "limit": 10, "window": 60, "bucket": "auth"},
    "/api/v1/auth/forgot-password": {"scope": "ip", "limit": 10, "window": 60, "bucket": "auth"},
    "/api/v1/auth/reset-password": {"scope": "ip", "limit": 10, "window": 60, "bucket": "auth"},
    "/api/v1/auth/refresh": {"scope": "ip", "limit": 20, "window": 60, "bucket": "refresh"},
    "/api/v1/auth/resend-verification": {"scope": "ip", "limit": 5, "window": 300, "bucket": "verify"},
    # Stricter limits for 2FA — prevents TOTP brute force (6-digit = 1M combos)
    "/api/v1/auth/2fa/verify-login": {
        "scope": "ip",
        "limit": 5,
        "window": 900,
        "bucket": "2fa",
        "detail": "Trop de tentatives. Réessaie dans 15 minutes.",
    },
    "/api/v1/auth/2fa/enable": {
        "scope": "ip",
        "limit": 5,
        "window": 900,
        "bucket": "2fa",
        "detail": "Trop de tentatives. Réessaie dans 15 minutes.",
    },
    "/api/v1/auth/2fa/disable": {
        "scope": "ip",
        "limit": 5,
        "window": 900,
        "bucket": "2fa",
        "detail": "Trop de tentatives. Réessaie dans 15 minutes.",
    },
    "/api/v1/billing/checkout-session": {
        "scope": "user_or_ip",
        "limit": 15,
        "window": 60,
        "bucket": "billing-checkout",
    },
    "/api/v1/billing/module-checkout-session": {
        "scope": "user_or_ip",
        "limit": 15,
        "window": 60,
        "bucket": "billing-module-checkout",
    },
    "/api/v1/billing/portal-session": {
        "scope": "user_or_ip",
        "limit": 15,
        "window": 60,
        "bucket": "billing-portal",
    },
    "/api/v1/billing/credits/purchase": {
        "scope": "user_or_ip",
        "limit": 10,
        "window": 60,
        "bucket": "billing-credits",
    },
    "/api/v1/billing/addon/checkout": {
        "scope": "user_or_ip",
        "limit": 10,
        "window": 60,
        "bucket": "billing-addon",
    },
    "/api/v1/admin/branding": {
        "scope": "user_or_ip",
        "limit": 30,
        "window": 60,
        "bucket": "admin-branding",
    },
    "/api/v1/modules/custom": {
        "scope": "user_or_ip",
        "limit": 20,
        "window": 60,
        "bucket": "modules-custom",
    },
}


def _rate_limit_key(scope: str, bucket: str, ip: str, user_id: str | None) -> str:
    if scope == "user_or_ip" and user_id:
        return f"ratelimit:user:{user_id}:{bucket}"
    return f"ratelimit:ip:{ip}:{bucket}"


@app.middleware("http")
async def rate_limit(request: Request, call_next) -> Response:
    path = request.url.path
    if any(path.startswith(p) for p in _RATE_SKIP_PREFIXES):
        return await call_next(request)

    ip = (request.client.host if request.client else "unknown").replace(":", "_")
    user_id = _extract_sub(request.headers.get("authorization"))
    rule = _RATE_LIMIT_RULES.get(path)

    if rule:
        key = _rate_limit_key(
            str(rule["scope"]),
            str(rule["bucket"]),
            ip,
            user_id,
        )
        limit = int(rule["limit"])
        window = int(rule["window"])
        detail = str(rule.get("detail", f"Too many requests. Réessaie dans {window} secondes."))
    elif path.startswith("/api/v1/admin"):
        key = _rate_limit_key("user_or_ip", "admin", ip, user_id)
        limit = 60
        window = 60
        detail = "Too many admin requests. Réessaie dans 60 secondes."
    else:
        key = _rate_limit_key("user_or_ip", "default", ip, user_id)
        limit = 100 if user_id else 30
        window = 60
        detail = "Too many requests. Réessaie dans 60 secondes."

    try:
        redis = await _get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window)
        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": detail},
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
app.include_router(admin_orchestrator.router, prefix="/api/v1/admin", tags=["admin-orchestrator"])
app.include_router(branding.router, prefix="/api/v1", tags=["branding"])
app.include_router(custom_modules.router, prefix="/api/v1", tags=["custom-modules"])
app.include_router(team.router, prefix="/api/v1", tags=["team"])
app.include_router(micro_saas.router, prefix="/api/v1", tags=["Micro-SaaS Builder"])
app.include_router(decision_engine.router, prefix="/api/v1", tags=["Decision Engine"])
app.include_router(knowledge_weapon.router, prefix="/api/v1", tags=["Knowledge Weapon"])
app.include_router(digital_leverage.router, prefix="/api/v1", tags=["Digital Leverage"])
app.include_router(reverse_engineering.router, prefix="/api/v1", tags=["Reverse Engineering"])
app.include_router(offer_generator.router, prefix="/api/v1", tags=["Offer Generator"])
app.include_router(execution_service.router, prefix="/api/v1", tags=["Execution Service"])
app.include_router(scrape.router, tags=["scraping"])
from api.routers.contact import router as contact_router
app.include_router(contact_router, prefix="/api/v1", tags=["contact"])

if settings.CHAOS_ENABLED:
    from api.routers.chaos import router as chaos_router
    app.include_router(chaos_router, tags=["chaos"])
