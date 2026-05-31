from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlsplit

from fastapi import HTTPException

from api.config import settings
from api.core.logging import get_correlation_id
from api.scraping.backoff import exponential_backoff_seconds
from api.scraping.cache import acquire_inflight_lock, read_cached_result, release_inflight_lock, write_cached_result
from api.scraping.feature_flags import async_queue_enabled
from api.scraping.fetcher import fetch_url
from api.scraping.metrics import (
    SCRAPE_CACHE_REQUESTS_TOTAL,
    SCRAPE_CIRCUIT_OPEN_TOTAL,
    SCRAPE_ERRORS_TOTAL,
    SCRAPE_LATENCY_SECONDS,
    SCRAPE_REDIRECTS_TOTAL,
    SCRAPE_REQUESTS_TOTAL,
    SCRAPE_RESPONSE_BYTES,
    SCRAPE_RETRIES_TOTAL,
)
from api.scraping.models import ScrapeJobEnqueueResponse, ScrapeJobState, ScrapeRequest, ScrapeResult
from api.scraping.queue import (
    build_request_dedupe_key,
    clear_job,
    client_quota_key,
    domain_limit_key,
    enqueue_request,
    find_active_job,
    release_client_queue_slot,
)
from api.scraping.security import normalized_hash, redact_url_for_logs, request_fingerprint, validate_safe_url
from api.scraping.store import circuit_get, circuit_set, get_job_state, incr_with_ttl, loads_json, set_job_state

logger = logging.getLogger(__name__)


def _domain(normalized_url: str) -> str:
    return (urlsplit(normalized_url).hostname or "").lower()


def _log_scrape_event(event: str, **fields: object) -> None:
    from api.core.logging import get_request_id
    from api.config import settings as runtime_settings

    safe_fields = {
        key: redact_url_for_logs(value) if key in {"url", "normalized_url"} and isinstance(value, str) else value
        for key, value in fields.items()
    }
    logger.info({"event": event, "traceId": get_request_id(), "region": runtime_settings.APP_REGION, **safe_fields})


async def _enforce_rate_limit(domain: str) -> None:
    count = await incr_with_ttl(domain_limit_key(domain), 60)
    if count > settings.SCRAPING_RATE_LIMIT_PER_DOMAIN_PER_MIN:
        raise HTTPException(status_code=429, detail="Domain rate limit exceeded")


async def _enforce_client_quota(client_id: str | None) -> None:
    if settings.SCRAPING_CLIENT_DAILY_QUOTA <= 0 or not client_id:
        return
    epoch_day = int(time.time()) // 86400
    key = client_quota_key(client_id, epoch_day)
    count = await incr_with_ttl(key, 86400)
    if count > settings.SCRAPING_CLIENT_DAILY_QUOTA:
        raise HTTPException(status_code=429, detail="Client daily quota exceeded")


async def _enforce_client_rate_limit(client_id: str | None) -> None:
    if settings.SCRAPING_RATE_LIMIT_CLIENT_PER_MIN <= 0 or not client_id:
        return
    count = await incr_with_ttl(f"scrape:rl:client:{client_id}", 60)
    if count > settings.SCRAPING_RATE_LIMIT_CLIENT_PER_MIN:
        raise HTTPException(status_code=429, detail="Client rate limit exceeded")


async def _check_circuit(domain: str) -> None:
    state = await circuit_get(domain)
    if int(state.get("opened_until", 0)) > int(time.time()):
        SCRAPE_ERRORS_TOTAL.labels(mode="sync", domain=domain, reason="circuit_open").inc()
        raise HTTPException(status_code=503, detail="Domain circuit breaker is open")


async def _record_failure(domain: str) -> None:
    state = await circuit_get(domain)
    failures = int(state.get("failures", 0)) + 1
    opened_until = 0
    if failures >= settings.SCRAPING_CIRCUIT_FAIL_THRESHOLD:
        opened_until = int(time.time()) + settings.SCRAPING_CIRCUIT_OPEN_SECONDS
        SCRAPE_CIRCUIT_OPEN_TOTAL.labels(domain=domain).inc()
    await circuit_set(domain, failures, opened_until, settings.SCRAPING_CIRCUIT_OPEN_SECONDS * 2)


async def _record_success(domain: str) -> None:
    await circuit_set(domain, 0, 0, settings.SCRAPING_CIRCUIT_OPEN_SECONDS * 2)


async def legacy_scrape_once(req: ScrapeRequest) -> ScrapeResult:
    normalized_url = validate_safe_url(req.url)
    domain = _domain(normalized_url)
    status_code, content_type, body, fetched_via, redirect_count, used_proxy = await fetch_url(
        normalized_url,
        render_js=req.render_js,
    )
    return ScrapeResult(
        url=req.url,
        normalized_url=normalized_url,
        domain=domain,
        status_code=status_code,
        content_type=content_type,
        body=body,
        fetched_via=fetched_via,
        cache_hit=False,
        stale=False,
        redirect_count=redirect_count,
        response_bytes=len(body.encode("utf-8", errors="replace")),
        used_proxy=used_proxy,
    )


async def scrape_once(req: ScrapeRequest) -> ScrapeResult:
    normalized_url = validate_safe_url(req.url)
    domain = _domain(normalized_url)
    request_hash = normalized_hash(request_fingerprint(normalized_url, render_js=req.render_js))
    started_at = time.perf_counter()

    if settings.SCRAPING_RISK_SCORING_ENABLED:
        from api.scraping.risk import is_risky

        if is_risky(normalized_url):
            raise HTTPException(status_code=403, detail="URL risk score too high")

    await _enforce_rate_limit(domain)
    await _enforce_client_rate_limit(req.client_id)
    await _enforce_client_quota(req.client_id)
    await _check_circuit(domain)

    if not req.force_refresh:
        cached = await read_cached_result(request_hash)
        if cached is not None:
            SCRAPE_CACHE_REQUESTS_TOTAL.labels(result="hit").inc()
            SCRAPE_REQUESTS_TOTAL.labels(mode=req.mode, outcome="cache_hit", domain=domain).inc()
            SCRAPE_LATENCY_SECONDS.labels(mode=req.mode, source="cache", domain=domain).observe(
                time.perf_counter() - started_at
            )
            _log_scrape_event(
                "scrape_cache_hit",
                url=req.url,
                normalized_url=normalized_url,
                domain=domain,
                mode=req.mode,
            )
            return cached
        SCRAPE_CACHE_REQUESTS_TOTAL.labels(result="miss").inc()

    lock_ok = await acquire_inflight_lock(request_hash)
    if not lock_ok:
        cached = await read_cached_result(request_hash, allow_stale=settings.SCRAPING_FEATURE_CACHE_FALLBACK_ENABLED)
        if cached is not None:
            return cached
        raise HTTPException(status_code=409, detail="Duplicate scrape in progress")

    last_exc: Exception | None = None
    try:
        for attempt in range(1, settings.SCRAPING_RETRY_MAX_ATTEMPTS + 1):
            try:
                status_code, content_type, body, fetched_via, redirect_count, used_proxy = await fetch_url(
                    normalized_url,
                    render_js=req.render_js,
                )
                result = ScrapeResult(
                    url=req.url,
                    normalized_url=normalized_url,
                    domain=domain,
                    status_code=status_code,
                    content_type=content_type,
                    body=body,
                    fetched_via=fetched_via,
                    cache_hit=False,
                    redirect_count=redirect_count,
                    response_bytes=len(body.encode("utf-8", errors="replace")),
                    used_proxy=used_proxy,
                )
                await write_cached_result(request_hash, result)
                await _record_success(domain)
                SCRAPE_REQUESTS_TOTAL.labels(mode=req.mode, outcome="success", domain=domain).inc()
                SCRAPE_LATENCY_SECONDS.labels(mode=req.mode, source=result.fetched_via, domain=domain).observe(
                    time.perf_counter() - started_at
                )
                SCRAPE_RESPONSE_BYTES.labels(mode=req.mode, source=result.fetched_via, domain=domain).observe(
                    result.response_bytes
                )
                if result.redirect_count:
                    SCRAPE_REDIRECTS_TOTAL.labels(mode=req.mode, source=result.fetched_via, domain=domain).inc(
                        result.redirect_count
                    )
                _log_scrape_event(
                    "scrape_completed",
                    url=req.url,
                    normalized_url=normalized_url,
                    domain=domain,
                    mode=req.mode,
                    source=result.fetched_via,
                    status_code=result.status_code,
                    cache_hit=False,
                    redirect_count=result.redirect_count,
                    response_bytes=result.response_bytes,
                    used_proxy=result.used_proxy,
                )
                return result
            except HTTPException as exc:
                if exc.status_code in {403, 429, 451}:
                    await _record_failure(domain)
                    SCRAPE_REQUESTS_TOTAL.labels(mode=req.mode, outcome="http_error", domain=domain).inc()
                    SCRAPE_ERRORS_TOTAL.labels(mode=req.mode, domain=domain, reason=str(exc.status_code)).inc()
                    raise
                await _record_failure(domain)
                SCRAPE_REQUESTS_TOTAL.labels(mode=req.mode, outcome="http_error", domain=domain).inc()
                SCRAPE_ERRORS_TOTAL.labels(mode=req.mode, domain=domain, reason=str(exc.status_code)).inc()
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                await _record_failure(domain)
                if attempt == settings.SCRAPING_RETRY_MAX_ATTEMPTS:
                    break
                SCRAPE_RETRIES_TOTAL.labels(mode=req.mode, domain=domain, reason=type(exc).__name__).inc()
                await asyncio.sleep(exponential_backoff_seconds(attempt))

        SCRAPE_REQUESTS_TOTAL.labels(mode=req.mode, outcome="failed", domain=domain).inc()
        SCRAPE_ERRORS_TOTAL.labels(
            mode=req.mode,
            domain=domain,
            reason=type(last_exc).__name__ if last_exc is not None else "unknown",
        ).inc()
        if settings.SCRAPING_FEATURE_CACHE_FALLBACK_ENABLED and not req.force_refresh:
            stale = await read_cached_result(request_hash, allow_stale=True)
            if stale is not None:
                _log_scrape_event(
                    "scrape_stale_fallback",
                    url=req.url,
                    normalized_url=normalized_url,
                    domain=domain,
                    mode=req.mode,
                )
                return stale
        logger.exception("scrape_failed", extra={"url": redact_url_for_logs(req.url), "domain": domain})
        raise HTTPException(status_code=502, detail=f"Scrape failed: {type(last_exc).__name__}")
    finally:
        await release_inflight_lock(request_hash)


async def enqueue_scrape(req: ScrapeRequest) -> ScrapeJobEnqueueResponse:
    if not async_queue_enabled():
        raise HTTPException(status_code=503, detail="Asynchronous scraping is disabled")

    normalized_url = validate_safe_url(req.url)
    domain = _domain(normalized_url)
    request_dedupe_key = build_request_dedupe_key(normalized_url, render_js=req.render_js)

    if settings.SCRAPING_RISK_SCORING_ENABLED:
        from api.scraping.risk import is_risky

        if is_risky(normalized_url):
            raise HTTPException(status_code=403, detail="URL risk score too high")

    await _enforce_rate_limit(domain)
    await _enforce_client_rate_limit(req.client_id)
    await _enforce_client_quota(req.client_id)
    await _check_circuit(domain)

    if not req.force_refresh:
        existing = await find_active_job(request_dedupe_key)
        if existing:
            _log_scrape_event(
                "scrape_job_deduped",
                url=req.url,
                normalized_url=normalized_url,
                domain=domain,
                job_id=existing["job_id"],
            )
            return ScrapeJobEnqueueResponse(job_id=existing["job_id"], status=existing["status"], queued=True)

    enqueue_response = await enqueue_request(
        req,
        normalized_url=normalized_url,
        request_dedupe_key=request_dedupe_key,
        correlation_id=get_correlation_id() or None,
    )
    _log_scrape_event(
        "scrape_job_enqueued",
        url=req.url,
        normalized_url=normalized_url,
        domain=domain,
        job_id=enqueue_response.job_id,
    )
    return enqueue_response


async def get_scrape_job(job_id: str) -> ScrapeJobState:
    raw = await get_job_state(job_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Scrape job not found")

    result_obj = None
    if raw.get("result") and raw["result"] not in {"None", "null"}:
        result_obj = ScrapeResult(**loads_json(raw["result"]))

    return ScrapeJobState(
        job_id=raw["job_id"],
        status=raw["status"],
        created_at=int(raw["created_at"]),
        updated_at=int(raw["updated_at"]),
        attempts=int(raw.get("attempts", "0")),
        normalized_url=raw.get("normalized_url", ""),
        correlation_id=raw.get("correlation_id") or None,
        result=result_obj,
        error=raw.get("error") or None,
    )


async def process_job(job_id: str) -> None:
    raw = await get_job_state(job_id)
    if not raw:
        return

    now = int(time.time())
    request_raw = raw.get("request")
    if not request_raw:
        await set_job_state(
            job_id,
            {
                **raw,
                "status": "failed",
                "updated_at": str(now),
                "error": "missing_request_payload",
            },
            settings.SCRAPING_JOB_TTL_SECONDS,
        )
        return

    req = ScrapeRequest.model_validate_json(request_raw)
    attempts = int(raw.get("attempts", "0")) + 1
    request_dedupe_key = build_request_dedupe_key(raw.get("normalized_url", req.url), render_js=req.render_js)

    await set_job_state(
        job_id,
        {
            **raw,
            "status": "processing",
            "attempts": str(attempts),
            "updated_at": str(now),
        },
        settings.SCRAPING_JOB_TTL_SECONDS,
    )

    try:
        result = await scrape_once(req)
        await set_job_state(
            job_id,
            {
                **raw,
                "status": "done",
                "attempts": str(attempts),
                "updated_at": str(int(time.time())),
                "result": result.model_dump_json(),
                "error": "",
            },
            settings.SCRAPING_JOB_TTL_SECONDS,
        )
        await release_client_queue_slot(req.client_id)
        await clear_job(request_dedupe_key, job_id)
    except Exception as exc:  # noqa: BLE001
        await set_job_state(
            job_id,
            {
                **raw,
                "status": "failed",
                "attempts": str(attempts),
                "updated_at": str(int(time.time())),
                "error": f"{type(exc).__name__}: {exc}",
            },
            settings.SCRAPING_JOB_TTL_SECONDS,
        )
        await release_client_queue_slot(req.client_id)
        await clear_job(request_dedupe_key, job_id)
