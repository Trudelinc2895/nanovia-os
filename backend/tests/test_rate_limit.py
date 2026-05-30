"""
Unit tests for rate limiting, body size middleware, and proxy pool.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


# ── middleware/body_limit.py ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_body_limit_passes_get_requests():
    """GET requests should pass through regardless of content-length."""
    from api.middleware.body_limit import BodySizeLimitMiddleware
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def homepage(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=10)
    client = TestClient(app)
    response = client.get("/", headers={"Content-Length": "999"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_body_limit_rejects_large_post():
    """POST with Content-Length exceeding the limit should get 413."""
    from api.middleware.body_limit import BodySizeLimitMiddleware
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def endpoint(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/upload", endpoint, methods=["POST"])])
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=100)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/upload",
        content=b"x" * 10,
        headers={"Content-Length": "1000"},
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_body_limit_passes_within_limit():
    """POST within the body size limit should be allowed."""
    from api.middleware.body_limit import BodySizeLimitMiddleware
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def endpoint(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/data", endpoint, methods=["POST"])])
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=1024)
    client = TestClient(app)
    response = client.post("/data", content=b"x" * 50)
    assert response.status_code == 200


# ── stealth/proxy_pool.py ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_proxy_pool_returns_none_when_empty():
    """ProxyPool with no proxies should return None."""
    from api.scraping.stealth.proxy_pool import ProxyPool
    pool = ProxyPool([], healthcheck_url="https://health.example/ip")
    result = await pool.get_proxy()
    assert result is None


@pytest.mark.asyncio
async def test_proxy_pool_round_robin():
    """ProxyPool should cycle through proxies in order."""
    from api.scraping.stealth.proxy_pool import ProxyPool
    pool = ProxyPool(["http://proxy1:3128", "http://proxy2:3128"], healthcheck_url="https://health.example/ip")
    first = await pool.get_proxy()
    second = await pool.get_proxy()
    assert first != second


@pytest.mark.asyncio
async def test_proxy_pool_skips_dead_proxy():
    """ProxyPool should skip proxies marked as dead."""
    from api.scraping.stealth.proxy_pool import ProxyPool
    pool = ProxyPool(["http://dead:3128", "http://alive:3128"], healthcheck_url="https://health.example/ip")
    await pool.mark_dead("http://dead:3128")
    result = await pool.get_proxy()
    assert result == "http://alive:3128"


@pytest.mark.asyncio
async def test_proxy_pool_returns_none_when_all_dead():
    """ProxyPool should return None when all proxies are dead."""
    from api.scraping.stealth.proxy_pool import ProxyPool
    pool = ProxyPool(["http://proxy1:3128"], healthcheck_url="https://health.example/ip")
    await pool.mark_dead("http://proxy1:3128")
    result = await pool.get_proxy()
    assert result is None


@pytest.mark.asyncio
async def test_proxy_pool_mark_dead_sets_expiry():
    """mark_dead should add proxy to the dead set with a future expiry."""
    import time
    from api.scraping.stealth.proxy_pool import ProxyPool
    pool = ProxyPool(["http://proxy1:3128"], healthcheck_url="https://health.example/ip")
    await pool.mark_dead("http://proxy1:3128")
    assert "http://proxy1:3128" in pool._dead
    assert pool._dead["http://proxy1:3128"] > time.time()


# ── config.py — new settings ──────────────────────────────────────────────────

def test_config_stealth_mode_defaults_false():
    """SCRAPING_STEALTH_MODE should default to False."""
    from api.config import settings
    assert settings.SCRAPING_STEALTH_MODE is False


def test_config_chaos_enabled_defaults_false():
    """CHAOS_ENABLED should default to False."""
    from api.config import settings
    assert settings.CHAOS_ENABLED is False


def test_config_risk_scoring_defaults_false():
    """SCRAPING_RISK_SCORING_ENABLED should default to False."""
    from api.config import settings
    assert settings.SCRAPING_RISK_SCORING_ENABLED is False


def test_config_body_size_limit_default():
    """API_BODY_SIZE_LIMIT_BYTES should default to 1MB."""
    from api.config import settings
    assert settings.API_BODY_SIZE_LIMIT_BYTES == 1_048_576


def test_config_api_key_budgets_default_zero():
    """Hourly and daily budgets should default to 0 (disabled)."""
    from api.config import settings
    assert settings.SCRAPING_API_KEY_HOURLY_BUDGET == 0
    assert settings.SCRAPING_API_KEY_DAILY_BUDGET == 0


def test_load_multiplier_disabled_in_development(monkeypatch):
    """Adaptive throttling should not shrink limits in development/test."""
    from api.main import _get_load_multiplier
    from api.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "development")
    assert _get_load_multiplier() == 1.0


def test_contact_route_has_strict_rate_limit():
    from api.main import _RATE_LIMIT_RULES

    assert _RATE_LIMIT_RULES["/api/v1/contact"] == {
        "scope": "ip",
        "limit": 5,
        "window": 300,
        "bucket": "contact",
        "detail": "Trop de messages de contact. Réessaie dans 5 minutes.",
    }


# ── health — /live endpoint ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_live_endpoint_returns_200():
    """GET /live should always return 200."""
    from httpx import AsyncClient, ASGITransport
    from api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_alias_returns_200_with_stubbed_dependencies(monkeypatch):
    """GET /ready should mirror readiness without requiring real Redis/Postgres."""
    import api.database as database_module
    import redis.asyncio as aioredis
    from httpx import ASGITransport, AsyncClient
    from api.main import app

    class _FakeDB:
        async def execute(self, _query):
            return 1

    async def _fake_get_db():
        yield _FakeDB()

    class _FakeRedis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    monkeypatch.setattr(database_module, "get_db", _fake_get_db)
    monkeypatch.setattr(aioredis, "from_url", lambda *_a, **_k: _FakeRedis())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_ready_alias_returns_503_when_postgres_unavailable(monkeypatch):
    """GET /ready should degrade when the database check fails."""
    import api.database as database_module
    import redis.asyncio as aioredis
    from httpx import ASGITransport, AsyncClient
    from api.main import app

    async def _broken_get_db():
        raise RuntimeError("postgres unavailable")
        yield  # pragma: no cover

    class _FakeRedis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    monkeypatch.setattr(database_module, "get_db", _broken_get_db)
    monkeypatch.setattr(aioredis, "from_url", lambda *_a, **_k: _FakeRedis())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@pytest.mark.asyncio
async def test_request_middleware_echoes_correlation_headers():
    """Request middleware should surface trace and correlation identifiers to clients."""
    from httpx import ASGITransport, AsyncClient
    from api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={"X-Request-ID": "trace-abc", "X-Correlation-ID": "corr-xyz"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-abc"
    assert response.headers["X-Correlation-ID"] == "corr-xyz"


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_worker_and_queue_metrics(monkeypatch):
    """GET /metrics should include refreshed scrape runtime metrics."""
    from httpx import ASGITransport, AsyncClient
    from api.main import app
    from api.scraping import store

    async def _fake_queue_depth() -> int:
        return 7

    async def _fake_get_worker_heartbeats() -> list[dict[str, str]]:
        return [
            {
                "worker_id": "worker-1",
                "region": "us-east-1",
                "status": "idle",
                "updated_at": "1700000000",
            }
        ]

    monkeypatch.setattr(store, "queue_depth", _fake_queue_depth)
    monkeypatch.setattr(store, "get_worker_heartbeats", _fake_get_worker_heartbeats)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "scrape_queue_depth 7.0" in response.text
    assert "scrape_worker_active 1.0" in response.text
