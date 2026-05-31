from __future__ import annotations

import asyncio

import httpx
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


def test_request_dedupe_key_separates_render_modes():
    from api.scraping.queue import build_request_dedupe_key

    assert build_request_dedupe_key("https://example.com", render_js=False) != build_request_dedupe_key(
        "https://example.com",
        render_js=True,
    )


def test_request_dedupe_key_strips_tracking_params():
    from api.scraping.queue import build_request_dedupe_key

    left = build_request_dedupe_key("https://example.com/page?utm_source=ad&a=1", render_js=False)
    right = build_request_dedupe_key("https://example.com/page?a=1", render_js=False)

    assert left == right


def test_build_job_id_is_stable_for_same_request():
    from api.scraping.queue import build_job_id

    left = build_job_id("https://example.com/page?a=1&utm_source=ad", render_js=True)
    right = build_job_id("https://example.com/page?a=1", render_js=True)

    assert left == right


def test_browser_request_target_blocks_cross_domain_redirect(monkeypatch):
    from api.scraping import fetcher_browser

    def fake_validate_redirect(_previous_url: str, _target_url: str) -> str:
        raise HTTPException(status_code=403, detail="Redirect target blocked")

    monkeypatch.setattr(fetcher_browser, "validate_redirect", fake_validate_redirect)

    with pytest.raises(HTTPException) as exc:
        fetcher_browser._validate_browser_request_target(
            "https://example.com/start",
            "https://other.example/path",
            initial=False,
        )

    assert exc.value.status_code == 403


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
    assert cached.stale is False


@pytest.mark.asyncio
async def test_cache_can_return_stale_entry(monkeypatch):
    from api.config import settings
    from api.scraping import cache
    from api.scraping.models import ScrapeResult

    state: dict[str, str] = {}
    clock = {"value": 1000}

    async def fake_cache_get(key: str) -> str | None:
        return state.get(key)

    async def fake_cache_setex(key: str, ttl: int, value: str) -> None:
        del ttl
        state[key] = value

    monkeypatch.setattr(cache, "cache_get", fake_cache_get)
    monkeypatch.setattr(cache, "cache_setex", fake_cache_setex)
    monkeypatch.setattr(cache.time, "time", lambda: clock["value"])
    monkeypatch.setattr(settings, "SCRAPING_CACHE_TTL_SECONDS", 10)
    monkeypatch.setattr(settings, "SCRAPING_CACHE_STALE_TTL_SECONDS", 20)

    result = ScrapeResult(
        url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
        status_code=200,
        content_type="text/html",
        body="<html />",
    )

    await cache.write_cached_result("stale", result)
    clock["value"] = 1015

    assert await cache.read_cached_result("stale") is None
    stale = await cache.read_cached_result("stale", allow_stale=True)
    assert stale is not None
    assert stale.cache_hit is True
    assert stale.stale is True


@pytest.mark.asyncio
async def test_store_cache_falls_back_locally_when_redis_is_down(monkeypatch):
    from api.scraping import store

    async def fake_get_redis():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(store, "get_redis", fake_get_redis)

    key = "scrape:test:cache-fallback"
    await store.cache_setex(key, 60, "cached-value")

    assert await store.cache_get(key) == "cached-value"


@pytest.mark.asyncio
async def test_store_queue_falls_back_locally_when_redis_is_down(monkeypatch):
    from api.scraping import store

    async def fake_get_redis():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(store, "get_redis", fake_get_redis)
    store._local_queue.clear()

    await store.enqueue_job("job-123")

    assert await store.dequeue_job(timeout_seconds=0) == "job-123"


@pytest.mark.asyncio
async def test_worker_heartbeat_falls_back_locally_when_redis_is_down(monkeypatch):
    from api.scraping import store

    async def fake_get_redis():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(store, "get_redis", fake_get_redis)
    await store.set_worker_heartbeat(
        "worker-a",
        {
            "worker_id": "worker-a",
            "region": "local",
            "status": "idle",
            "updated_at": "1700000000",
        },
        ttl=30,
    )

    heartbeats = await store.get_worker_heartbeats()

    assert heartbeats == [
        {
            "worker_id": "worker-a",
            "region": "local",
            "status": "idle",
            "updated_at": "1700000000",
        }
    ]


def test_validate_redirect_blocks_cross_domain(monkeypatch):
    from api.scraping import security

    def _fake_getaddrinfo(host, port, family=0, type=0):
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
async def test_fetch_url_does_not_mark_proxy_dead_on_http_exception(monkeypatch):
    from api.config import settings
    from api.scraping import fetcher

    marked: list[str] = []

    async def fake_fetch_http(normalized_url: str, *, proxy: str | None, request_headers: dict[str, str]):
        raise HTTPException(status_code=415, detail="Unsupported content-type")

    async def fake_mark_proxy_dead(proxy: str) -> None:
        marked.append(proxy)

    async def fake_choose_proxy_stealth(_domain: str) -> str:
        return "http://user:pass@proxy.example:8080"

    monkeypatch.setattr(settings, "SCRAPING_STEALTH_MODE", True)
    monkeypatch.setattr(settings, "SCRAPING_PROXY_ROTATION_ENABLED", True)
    monkeypatch.setattr(fetcher, "choose_proxy_stealth", fake_choose_proxy_stealth)
    monkeypatch.setattr(fetcher, "fetch_http", fake_fetch_http)
    monkeypatch.setattr(fetcher, "mark_proxy_dead", fake_mark_proxy_dead)

    with pytest.raises(HTTPException) as exc:
        await fetcher.fetch_url("https://example.com", render_js=False)

    assert exc.value.status_code == 415
    assert marked == []


@pytest.mark.asyncio
async def test_fetch_url_marks_proxy_dead_on_transport_error(monkeypatch):
    from api.config import settings
    from api.scraping import fetcher

    marked: list[str] = []

    async def fake_fetch_http(normalized_url: str, *, proxy: str | None, request_headers: dict[str, str]):
        request = httpx.Request("GET", normalized_url)
        raise httpx.ConnectError("proxy failed", request=request)

    async def fake_mark_proxy_dead(proxy: str) -> None:
        marked.append(proxy)

    async def fake_choose_proxy_stealth(_domain: str) -> str:
        return "http://user:pass@proxy.example:8080"

    monkeypatch.setattr(settings, "SCRAPING_STEALTH_MODE", True)
    monkeypatch.setattr(settings, "SCRAPING_PROXY_ROTATION_ENABLED", True)
    monkeypatch.setattr(fetcher, "choose_proxy_stealth", fake_choose_proxy_stealth)
    monkeypatch.setattr(fetcher, "fetch_http", fake_fetch_http)
    monkeypatch.setattr(fetcher, "mark_proxy_dead", fake_mark_proxy_dead)

    with pytest.raises(httpx.ConnectError):
        await fetcher.fetch_url("https://example.com", render_js=False)

    assert marked == ["http://user:pass@proxy.example:8080"]


@pytest.mark.asyncio
async def test_fetch_browser_uses_stealth_context_options(monkeypatch):
    from api.config import settings
    from api.scraping import fetcher_browser

    captured: dict[str, object] = {}

    class _FakePage:
        def __init__(self) -> None:
            self.main_frame = object()
            self.url = "https://example.com"

        async def route(self, _pattern, _handler) -> None:
            return None

        async def set_extra_http_headers(self, headers) -> None:
            captured["headers"] = headers

        async def goto(self, _url, wait_until, timeout):
            captured["goto"] = {"wait_until": wait_until, "timeout": timeout}
            return type("Response", (), {"status": 200})()

        def unroute(self, _pattern, _handler):
            return None

        async def content(self) -> str:
            return "<html />"

    class _FakePageContext:
        async def __aenter__(self):
            return _FakePage()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    def fake_page(*, context_options=None):
        captured["context_options"] = context_options
        return _FakePageContext()

    monkeypatch.setattr(settings, "SCRAPING_STEALTH_MODE", True)
    monkeypatch.setattr(settings, "SCRAPING_STEALTH_TIMEZONE", "America/Toronto")
    monkeypatch.setattr(settings, "SCRAPING_STEALTH_VIEWPORT_WIDTH", 1440)
    monkeypatch.setattr(settings, "SCRAPING_STEALTH_VIEWPORT_HEIGHT", 900)
    monkeypatch.setattr(fetcher_browser._browser_pool, "page", fake_page)
    monkeypatch.setattr(fetcher_browser, "check_content_safety", lambda _html, _url: True)
    monkeypatch.setattr(fetcher_browser, "validate_safe_url", lambda url: url)
    monkeypatch.setattr("api.scraping.stealth.fingerprint.apply_stealth_patches", lambda page, profile=None: asyncio.sleep(0))
    monkeypatch.setattr("api.scraping.stealth.behavior.wait_for_content", lambda page: asyncio.sleep(0))

    profile = {
        "ua": "TestBrowser/1.0",
        "locale": "fr-CA",
    }
    headers = {"User-Agent": "TestBrowser/1.0", "Accept-Language": "fr-CA,fr;q=0.9"}

    status_code, content_type, body, fetched_via, redirect_count, used_proxy = await fetcher_browser.fetch_browser(
        "https://example.com",
        proxy=None,
        request_headers=headers,
        stealth_profile=profile,
    )

    assert status_code == 200
    assert content_type == "text/html"
    assert body == "<html />"
    assert fetched_via == "playwright"
    assert redirect_count == 0
    assert used_proxy is False
    assert captured["context_options"] == {
        "user_agent": "TestBrowser/1.0",
        "locale": "fr-CA",
        "timezone_id": "America/Toronto",
        "viewport": {"width": 1440, "height": 900},
    }


@pytest.mark.asyncio
async def test_scrape_once_does_not_retry_on_bot_block(monkeypatch):
    from api.scraping import service
    from api.scraping.models import ScrapeRequest

    attempts = {"count": 0}

    async def fake_enforce(*args, **kwargs):
        return None

    async def fake_fetch_url(_normalized_url: str, *, render_js: bool):
        attempts["count"] += 1
        raise HTTPException(status_code=403, detail="Bot detection page - request blocked")

    monkeypatch.setattr(service, "validate_safe_url", lambda url: url)
    monkeypatch.setattr(service, "_domain", lambda _url: "example.com")
    monkeypatch.setattr(
        service,
        "read_cached_result",
        lambda _key, allow_stale=False: asyncio.sleep(0, result=None),
    )
    monkeypatch.setattr(service, "acquire_inflight_lock", lambda _key: asyncio.sleep(0, result=True))
    monkeypatch.setattr(service, "_enforce_rate_limit", fake_enforce)
    monkeypatch.setattr(service, "_enforce_client_quota", fake_enforce)
    monkeypatch.setattr(service, "_check_circuit", fake_enforce)
    monkeypatch.setattr(service, "_record_failure", fake_enforce)
    monkeypatch.setattr(service, "fetch_url", fake_fetch_url)

    req = ScrapeRequest(url="https://example.com", mode="sync", render_js=True, force_refresh=False, client_id="client-1")

    with pytest.raises(HTTPException) as exc:
        await service.scrape_once(req)

    assert exc.value.status_code == 403
    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_scrape_once_releases_inflight_lock_after_failure(monkeypatch):
    from api.scraping import service
    from api.scraping.models import ScrapeRequest

    released: list[str] = []

    async def fake_enforce(*args, **kwargs):
        return None

    async def fake_fetch_url(_normalized_url: str, *, render_js: bool):
        raise RuntimeError("network exploded")

    async def fake_release(url_hash: str) -> None:
        released.append(url_hash)

    monkeypatch.setattr(service, "validate_safe_url", lambda url: url)
    monkeypatch.setattr(service, "_domain", lambda _url: "example.com")
    monkeypatch.setattr(service, "normalized_hash", lambda value: f"hash:{value}")
    monkeypatch.setattr(
        service,
        "read_cached_result",
        lambda _key, allow_stale=False: asyncio.sleep(0, result=None),
    )
    monkeypatch.setattr(service, "acquire_inflight_lock", lambda _key: asyncio.sleep(0, result=True))
    monkeypatch.setattr(service, "release_inflight_lock", fake_release)
    monkeypatch.setattr(service, "_enforce_rate_limit", fake_enforce)
    monkeypatch.setattr(service, "_enforce_client_quota", fake_enforce)
    monkeypatch.setattr(service, "_check_circuit", fake_enforce)
    monkeypatch.setattr(service, "_record_failure", fake_enforce)
    monkeypatch.setattr(service, "fetch_url", fake_fetch_url)

    req = ScrapeRequest(url="https://example.com", mode="sync", render_js=False, force_refresh=False, client_id="client-1")

    with pytest.raises(HTTPException) as exc:
        await service.scrape_once(req)

    assert exc.value.status_code == 502
    assert released == ["hash:https://example.com/|render_js=0"]


@pytest.mark.asyncio
async def test_mark_proxy_dead_redacts_proxy_credentials_in_logs(monkeypatch, caplog):
    from api.scraping import proxy_manager
    from api.scraping.stealth import proxy_pool

    async def fake_mark_proxy_dead(_proxy: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(proxy_pool, "mark_proxy_dead", fake_mark_proxy_dead)

    with caplog.at_level("WARNING"):
        await proxy_manager.mark_proxy_dead("http://user:pass@proxy.example:8080")

    assert caplog.records
    assert getattr(caplog.records[-1], "proxy") == "http://proxy.example:8080"


@pytest.mark.asyncio
async def test_enqueue_request_uses_opaque_public_job_id(monkeypatch):
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
    expected_request_dedupe_key = queue.build_request_dedupe_key("https://example.com", render_js=True)

    response = await queue.enqueue_request(
        req,
        normalized_url="https://example.com",
        request_dedupe_key=expected_request_dedupe_key,
    )

    expected_job_id = queue.build_job_id("https://example.com", render_js=True)

    assert response.job_id == expected_job_id
    assert captured["job_id"] == expected_job_id
    assert captured["payload_job_id"] == expected_job_id
    assert captured["dedupe_job_id"] == expected_job_id
    assert captured["queued_job_id"] == expected_job_id


@pytest.mark.asyncio
async def test_enqueue_request_releases_client_slot_when_queue_is_full(monkeypatch):
    from api.scraping import queue
    from api.scraping.models import ScrapeRequest

    released: list[str | None] = []

    async def fake_reserve_client_queue_slot(_client_id: str | None) -> None:
        return None

    async def fake_ensure_queue_capacity() -> int:
        raise HTTPException(status_code=503, detail="Scrape queue is full")

    async def fake_release_client_queue_slot(client_id: str | None) -> None:
        released.append(client_id)

    monkeypatch.setattr(queue, "reserve_client_queue_slot", fake_reserve_client_queue_slot)
    monkeypatch.setattr(queue, "ensure_queue_capacity", fake_ensure_queue_capacity)
    monkeypatch.setattr(queue, "release_client_queue_slot", fake_release_client_queue_slot)

    req = ScrapeRequest(url="https://example.com", mode="async", render_js=False, force_refresh=False, client_id="client-1")

    with pytest.raises(HTTPException) as exc:
        await queue.enqueue_request(
            req,
            normalized_url="https://example.com",
            request_dedupe_key=queue.build_request_dedupe_key("https://example.com", render_js=False),
        )

    assert exc.value.status_code == 503
    assert released == ["client-1"]


@pytest.mark.asyncio
async def test_worker_get_job_domain_reads_request_payload(monkeypatch):
    from api.scraping import worker

    async def fake_get_job_state(_job_id: str) -> dict[str, str]:
        return {
            "request": '{"url":"https://example.com/path","mode":"async","render_js":false,"force_refresh":false,"client_id":"client-1"}',
            "normalized_url": "https://example.com/path",
        }

    monkeypatch.setattr("api.scraping.store.get_job_state", fake_get_job_state)

    assert await worker._get_job_domain("job-123") == "example.com"


@pytest.mark.asyncio
async def test_proxy_pool_health_check_uses_configured_url(monkeypatch):
    from api.scraping.stealth.proxy_pool import ProxyPool

    seen: list[str] = []

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str):
            seen.append(url)
            return type("Response", (), {"status_code": 200})()

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: _FakeClient())

    pool = ProxyPool(["http://proxy.example:8080"], healthcheck_url="https://health.example/ip")
    await pool.health_check_all()

    assert seen == ["https://health.example/ip"]


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
