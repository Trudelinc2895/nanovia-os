from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException


def test_exponential_backoff_grows(monkeypatch):
    from api.scraping import backoff

    monkeypatch.setattr(backoff.random, "uniform", lambda _a, _b: 0.0)
    assert backoff.exponential_backoff_seconds(1) == 0.25
    assert backoff.exponential_backoff_seconds(2) == 0.5


def test_proxy_manager_bypasses_configured_domains(monkeypatch):
    from api.config import settings
    from api.scraping.proxy_manager import choose_proxy

    monkeypatch.setattr(settings, "SCRAPING_FEATURE_PROXY_ENABLED", True)
    monkeypatch.setattr(settings, "SCRAPING_PROXY_ROTATION_ENABLED", True)
    monkeypatch.setattr(settings, "SCRAPING_PROXY_LIST_RAW", "http://proxy-a,http://proxy-b")
    monkeypatch.setattr(settings, "SCRAPING_PROXY_BYPASS_DOMAINS_RAW", "example.com")

    assert choose_proxy("api.example.com") is None


@pytest.mark.asyncio
async def test_cache_roundtrip(monkeypatch):
    from api.scraping import cache
    from api.scraping.models import ScrapeResult

    state: dict[str, str] = {}

    async def fake_cache_get(key: str) -> str | None:
        return state.get(key)

    async def fake_cache_setex(key: str, ttl: int, value: str) -> None:
        state[key] = value

    monkeypatch.setattr(cache, "cache_get", fake_cache_get)
    monkeypatch.setattr(cache, "cache_setex", fake_cache_setex)

    result = ScrapeResult(
        url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
        status_code=200,
        content_type="text/html",
        body="<html />",
    )

    await cache.write_cached_result("abc", result)
    cached = await cache.read_cached_result("abc")

    assert cached is not None
    assert cached.cache_hit is True
    assert cached.domain == "example.com"


def test_validate_redirect_blocks_cross_domain(monkeypatch):
    from api.scraping import security

    def _fake_getaddrinfo(host, port):
        return [("family", "type", "proto", "", ("93.184.216.34", 0))]

    monkeypatch.setattr("api.scraping.security.socket.getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_STRICT_ALLOWLIST", False)

    with pytest.raises(HTTPException) as exc:
        security.validate_redirect("https://example.com/start", "https://other.example/path")

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_client_queue_limit_releases_counter(monkeypatch):
    from api.config import settings
    from api.scraping import queue
    from api.scraping.models import ScrapeRequest

    counters: dict[str, int] = {}

    async def fake_incr_with_ttl(key: str, ttl: int) -> int:
        counters[key] = counters.get(key, 0) + 1
        return counters[key]

    async def fake_decr_with_floor(key: str) -> int:
        counters[key] = max(counters.get(key, 0) - 1, 0)
        return counters[key]

    monkeypatch.setattr(settings, "SCRAPING_CLIENT_MAX_QUEUED_JOBS", 1)
    monkeypatch.setattr(queue, "incr_with_ttl", fake_incr_with_ttl)
    monkeypatch.setattr(queue, "decr_with_floor", fake_decr_with_floor)

    await queue.reserve_client_queue_slot("client-1")

    with pytest.raises(HTTPException) as exc:
        await queue.reserve_client_queue_slot("client-1")

    assert exc.value.status_code == 429
    assert counters[queue.client_queue_key("client-1")] == 1


@pytest.mark.asyncio
async def test_ensure_queue_capacity_blocks_at_max(monkeypatch):
    from api.config import settings
    from api.scraping import queue

    async def fake_queue_depth() -> int:
        return 3

    monkeypatch.setattr(settings, "SCRAPING_QUEUE_MAX_DEPTH", 3)
    monkeypatch.setattr(queue, "queue_depth", fake_queue_depth)

    with pytest.raises(HTTPException) as exc:
        await queue.ensure_queue_capacity()

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_fetch_url_falls_back_to_http_when_browser_flag_disabled(monkeypatch):
    from api.scraping import fetcher

    async def fake_fetch_http(normalized_url: str, *, proxy: str | None, request_headers: dict[str, str]):
        return 200, "text/html", "<html />", 0, False

    async def fake_fetch_browser(normalized_url: str, *, proxy: str | None, request_headers: dict[str, str]):
        raise AssertionError("browser fetch should not be called")

    monkeypatch.setattr(fetcher, "browser_rendering_enabled", lambda: False)
    monkeypatch.setattr(fetcher, "fetch_http", fake_fetch_http)
    monkeypatch.setattr(fetcher, "fetch_browser", fake_fetch_browser)
    monkeypatch.setattr(fetcher, "choose_proxy", lambda _domain: None)

    status_code, content_type, body, fetched_via, redirect_count, used_proxy = await fetcher.fetch_url(
        "https://example.com",
        render_js=True,
    )

    assert status_code == 200
    assert content_type == "text/html"
    assert body == "<html />"
    assert fetched_via == "http"
    assert redirect_count == 0
    assert used_proxy is False


@pytest.mark.asyncio
async def test_enqueue_request_uses_stable_hashed_job_id(monkeypatch):
    from api.scraping import queue
    from api.scraping.models import ScrapeRequest

    captured: dict[str, str] = {}

    async def fake_reserve_client_queue_slot(_client_id: str | None) -> None:
        return None

    async def fake_ensure_queue_capacity() -> int:
        return 0

    async def fake_set_job_state(job_id: str, payload: dict[str, str], _ttl: int) -> None:
        captured["job_id"] = job_id
        captured["payload_job_id"] = payload["job_id"]

    async def fake_set_dedupe_job(_url_hash: str, job_id: str, _ttl: int) -> None:
        captured["dedupe_job_id"] = job_id

    async def fake_enqueue_job(job_id: str) -> None:
        captured["queued_job_id"] = job_id

    monkeypatch.setattr(queue, "reserve_client_queue_slot", fake_reserve_client_queue_slot)
    monkeypatch.setattr(queue, "ensure_queue_capacity", fake_ensure_queue_capacity)
    monkeypatch.setattr(queue, "set_job_state", fake_set_job_state)
    monkeypatch.setattr(queue, "set_dedupe_job", fake_set_dedupe_job)
    monkeypatch.setattr(queue, "enqueue_job", fake_enqueue_job)

    req = ScrapeRequest(url="https://example.com", mode="async", render_js=True, force_refresh=False, client_id="client-1")
    expected_job_id = queue.build_job_id("https://example.com", render_js=True)

    response = await queue.enqueue_request(req, normalized_url="https://example.com", url_hash="url-hash")

    assert response.job_id == expected_job_id
    assert captured["job_id"] == expected_job_id
    assert captured["payload_job_id"] == expected_job_id
    assert captured["dedupe_job_id"] == expected_job_id
    assert captured["queued_job_id"] == expected_job_id


@pytest.mark.asyncio
async def test_browser_pool_shutdown_cleans_up_resources():
    from api.scraping.fetcher_browser import BrowserPool

    class _FakeBrowser:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class _FakePlaywright:
        def __init__(self) -> None:
            self.stopped = False

        async def stop(self) -> None:
            self.stopped = True

    pool = BrowserPool(size=1)
    browser = _FakeBrowser()
    playwright = _FakePlaywright()
    zombie_task = asyncio.create_task(asyncio.sleep(60))

    pool._browser = browser
    pool._pw = playwright
    pool._zombie_task = zombie_task

    await pool.shutdown()

    assert browser.closed is True
    assert playwright.stopped is True
    assert zombie_task.cancelled() is True
    assert pool._browser is None
    assert pool._pw is None
    assert pool._zombie_task is None
