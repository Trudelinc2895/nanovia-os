from __future__ import annotations

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_scrape_once_uses_stale_cache_after_fetch_failure(monkeypatch):
    from api.scraping import service
    from api.scraping.models import ScrapeRequest, ScrapeResult

    async def fake_read_cached_result(_request_hash: str, *, allow_stale: bool = False):
        if not allow_stale:
            return None
        return ScrapeResult(
            url="https://example.com",
            normalized_url="https://example.com",
            domain="example.com",
            status_code=200,
            content_type="text/html",
            body="<html>stale</html>",
            cache_hit=True,
            stale=True,
        )

    async def fake_acquire_inflight_lock(_request_hash: str) -> bool:
        return True

    async def fake_release_inflight_lock(_request_hash: str) -> None:
        return None

    async def fake_fetch_url(_normalized_url: str, *, render_js: bool):
        del render_js
        raise RuntimeError("upstream unavailable")

    async def fake_noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "read_cached_result", fake_read_cached_result)
    monkeypatch.setattr(service, "acquire_inflight_lock", fake_acquire_inflight_lock)
    monkeypatch.setattr(service, "release_inflight_lock", fake_release_inflight_lock)
    monkeypatch.setattr(service, "fetch_url", fake_fetch_url)
    monkeypatch.setattr(service, "_enforce_rate_limit", fake_noop)
    monkeypatch.setattr(service, "_enforce_client_rate_limit", fake_noop)
    monkeypatch.setattr(service, "_enforce_client_quota", fake_noop)
    monkeypatch.setattr(service, "_check_circuit", fake_noop)
    monkeypatch.setattr(service, "_record_failure", fake_noop)
    monkeypatch.setattr(service, "_record_success", fake_noop)
    monkeypatch.setattr(service, "validate_safe_url", lambda url: url)
    monkeypatch.setattr(service.settings, "SCRAPING_FEATURE_CACHE_FALLBACK_ENABLED", True)
    monkeypatch.setattr(service.settings, "SCRAPING_RETRY_MAX_ATTEMPTS", 1)

    result = await service.scrape_once(ScrapeRequest(url="https://example.com", client_id="client-1"))

    assert result.cache_hit is True
    assert result.stale is True
    assert result.body == "<html>stale</html>"


@pytest.mark.asyncio
async def test_scrape_once_applies_client_per_minute_limit(monkeypatch):
    from api.scraping import service

    counts = {"scrape:rl:client:client-1": 0}

    async def fake_incr_with_ttl(key: str, ttl: int) -> int:
        del ttl
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(service, "incr_with_ttl", fake_incr_with_ttl)
    monkeypatch.setattr(service.settings, "SCRAPING_RATE_LIMIT_CLIENT_PER_MIN", 1)

    await service._enforce_client_rate_limit("client-1")
    with pytest.raises(HTTPException) as exc:
        await service._enforce_client_rate_limit("client-1")

    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_enqueue_scrape_includes_correlation_id(monkeypatch):
    from api.scraping import service
    from api.scraping.models import ScrapeJobEnqueueResponse, ScrapeRequest

    async def fake_enforce(*_args, **_kwargs):
        return None

    async def fake_find_active_job(_request_dedupe_key: str):
        return None

    async def fake_enqueue_request(req, *, normalized_url: str, request_dedupe_key: str, correlation_id: str | None = None):
        del req, normalized_url, request_dedupe_key
        return ScrapeJobEnqueueResponse(
            job_id="scrape-abc",
            status="queued",
            mode="async",
            queued=True,
            correlation_id=correlation_id,
        )

    monkeypatch.setattr(service, "_enforce_rate_limit", fake_enforce)
    monkeypatch.setattr(service, "_enforce_client_rate_limit", fake_enforce)
    monkeypatch.setattr(service, "_enforce_client_quota", fake_enforce)
    monkeypatch.setattr(service, "_check_circuit", fake_enforce)
    monkeypatch.setattr(service, "validate_safe_url", lambda url: url)
    monkeypatch.setattr(service, "find_active_job", fake_find_active_job)
    monkeypatch.setattr(service, "enqueue_request", fake_enqueue_request)
    monkeypatch.setattr(service, "get_correlation_id", lambda: "corr-123")
    monkeypatch.setattr(service.settings, "SCRAPING_ENABLED", True)
    monkeypatch.setattr(service.settings, "SCRAPING_PROXY_LAYER_ENABLED", True)
    monkeypatch.setattr(service.settings, "SCRAPING_FEATURE_ASYNC_QUEUE_ENABLED", True)

    response = await service.enqueue_scrape(ScrapeRequest(url="https://example.com", mode="async", client_id="client-1"))

    assert response.correlation_id == "corr-123"
