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
    pool = ProxyPool([])
    result = await pool.get_proxy()
    assert result is None


@pytest.mark.asyncio
async def test_proxy_pool_round_robin():
    """ProxyPool should cycle through proxies in order."""
    from api.scraping.stealth.proxy_pool import ProxyPool
    pool = ProxyPool(["http://proxy1:3128", "http://proxy2:3128"])
    first = await pool.get_proxy()
    second = await pool.get_proxy()
    assert first != second


@pytest.mark.asyncio
async def test_proxy_pool_skips_dead_proxy():
    """ProxyPool should skip proxies marked as dead."""
    from api.scraping.stealth.proxy_pool import ProxyPool
    pool = ProxyPool(["http://dead:3128", "http://alive:3128"])
    await pool.mark_dead("http://dead:3128")
    result = await pool.get_proxy()
    assert result == "http://alive:3128"


@pytest.mark.asyncio
async def test_proxy_pool_returns_none_when_all_dead():
    """ProxyPool should return None when all proxies are dead."""
    from api.scraping.stealth.proxy_pool import ProxyPool
    pool = ProxyPool(["http://proxy1:3128"])
    await pool.mark_dead("http://proxy1:3128")
    result = await pool.get_proxy()
    assert result is None


@pytest.mark.asyncio
async def test_proxy_pool_mark_dead_sets_expiry():
    """mark_dead should add proxy to the dead set with a future expiry."""
    import time
    from api.scraping.stealth.proxy_pool import ProxyPool
    pool = ProxyPool(["http://proxy1:3128"])
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
