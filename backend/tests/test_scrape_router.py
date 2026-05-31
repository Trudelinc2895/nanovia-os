from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from api.main import app


def test_scrape_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}

    assert "/scrape" in paths
    assert "/scrape/jobs/{job_id}" in paths


def test_scrape_route_returns_sync_payload_when_enabled(monkeypatch) -> None:
    from api.routers import scrape as scrape_router

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(app.router, "lifespan_context", _noop_lifespan)
    monkeypatch.setattr(scrape_router.settings, "SCRAPING_ENABLED", True)
    monkeypatch.setattr(scrape_router.settings, "SCRAPING_PROXY_LAYER_ENABLED", True)

    async def fake_scrape_once(req):
        return {
            "url": req.url,
            "mode": req.mode,
            "render_js": req.render_js,
            "force_refresh": req.force_refresh,
            "client_id": req.client_id,
        }

    monkeypatch.setattr(scrape_router, "scrape_once", fake_scrape_once)

    with TestClient(app) as client:
        response = client.get("/scrape", params={"url": "https://example.com/path?a=1"})

    assert response.status_code == 200
    assert response.json() == {
        "url": "https://example.com/path?a=1",
        "mode": scrape_router.settings.SCRAPING_MODE_DEFAULT,
        "render_js": False,
        "force_refresh": False,
        "client_id": "testclient",
    }


def test_scrape_route_uses_legacy_flow_when_proxy_layer_disabled(monkeypatch) -> None:
    from api.routers import scrape as scrape_router

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(app.router, "lifespan_context", _noop_lifespan)
    monkeypatch.setattr(scrape_router.settings, "SCRAPING_ENABLED", True)
    monkeypatch.setattr(scrape_router.settings, "SCRAPING_PROXY_LAYER_ENABLED", False)

    async def fake_legacy_scrape_once(req):
        return {"url": req.url, "legacy": True, "client_id": req.client_id}

    monkeypatch.setattr(scrape_router, "legacy_scrape_once", fake_legacy_scrape_once)

    with TestClient(app) as client:
        response = client.get("/scrape", params={"url": "https://example.com"})

    assert response.status_code == 200
    assert response.json() == {
        "url": "https://example.com",
        "legacy": True,
        "client_id": "testclient",
    }


def test_scrape_route_falls_back_to_sync_when_async_queue_unavailable(monkeypatch) -> None:
    from fastapi import HTTPException
    from api.routers import scrape as scrape_router

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(app.router, "lifespan_context", _noop_lifespan)
    monkeypatch.setattr(scrape_router.settings, "SCRAPING_ENABLED", True)
    monkeypatch.setattr(scrape_router.settings, "SCRAPING_PROXY_LAYER_ENABLED", True)
    monkeypatch.setattr(scrape_router.settings, "SCRAPING_FALLBACK_DIRECT_ENABLED", True)

    async def fake_enqueue_scrape(_req):
        raise HTTPException(status_code=503, detail="queue unavailable")

    async def fake_scrape_once(req):
        return {"url": req.url, "mode": req.mode, "fallback": "direct"}

    monkeypatch.setattr(scrape_router, "enqueue_scrape", fake_enqueue_scrape)
    monkeypatch.setattr(scrape_router, "scrape_once", fake_scrape_once)

    with TestClient(app) as client:
        response = client.get("/scrape", params={"url": "https://example.com", "mode": "async"})

    assert response.status_code == 200
    assert response.json() == {
        "url": "https://example.com",
        "mode": "sync",
        "fallback": "direct",
    }


def test_scrape_route_is_404_when_disabled(monkeypatch) -> None:
    from api.routers import scrape as scrape_router

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(app.router, "lifespan_context", _noop_lifespan)
    monkeypatch.setattr(scrape_router.settings, "SCRAPING_ENABLED", False)

    with TestClient(app) as client:
        response = client.get("/scrape", params={"url": "https://example.com"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Scraping is disabled"}
