from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException

from api.config import settings
from api.scraping.fetcher import fetch_url
from api.scraping.metrics import (
    SCRAPE_CIRCUIT_OPEN_TOTAL,
    SCRAPE_LATENCY_SECONDS,
    SCRAPE_QUEUE_DEPTH,
    SCRAPE_REQUESTS_TOTAL,
)
from api.scraping.models import ScrapeJobEnqueueResponse, ScrapeJobState, ScrapeRequest, ScrapeResult
from api.scraping.security import normalized_hash, validate_safe_url
from api.scraping.store import (
    cache_get,
    cache_setex,
    clear_dedupe_job,
    circuit_get,
    circuit_set,
    dumps_json,
    enqueue_job,
    get_dedupe_job,
    get_job_state,
    incr_with_ttl,
    loads_json,
    queue_depth,
    set_dedupe_job,
    set_job_state,
    setnx_with_ttl,
)

logger = logging.getLogger(__name__)


def _domain(normalized_url: str) -> str:
    return (urlsplit(normalized_url).hostname or "").lower()


def _cache_key(url_hash: str) -> str:
    return f"scrape:cache:{url_hash}"


def _inflight_key(url_hash: str) -> str:
    return f"scrape:inflight:{url_hash}"


def _domain_limit_key(domain: str) -> str:
    return f"scrape:rl:domain:{domain}"


def _client_quota_key(client_id: str, epoch_day: int) -> str:
    return f"scrape:quota:{client_id}:{epoch_day}"


def _log_scrape_event(event: str, **fields: object) -> None:
    logger.info({"event": event, **fields})


async def _enforce_rate_limit(domain: str) -> None:
    count = await incr_with_ttl(_domain_limit_key(domain), 60)
    if count > settings.SCRAPING_RATE_LIMIT_PER_DOMAIN_PER_MIN:
        raise HTTPException(status_code=429, detail="Domain rate limit exceeded")


async def _enforce_client_quota(client_id: str | None) -> None:
    if settings.SCRAPING_CLIENT_DAILY_QUOTA <= 0:
        return
    if not client_id:
        return
    epoch_day = int(time.time()) // 86400
    key = _client_quota_key(client_id, epoch_day)
    count = await incr_with_ttl(key, 86400)
    if count > settings.SCRAPING_CLIENT_DAILY_QUOTA:
        raise HTTPException(status_code=429, detail="Client daily quota exceeded")


async def _check_circuit(domain: str) -> None:
    state = await circuit_get(domain)
    if int(state.get("opened_until", 0)) > int(time.time()):
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


async def _read_cache(url_hash: str) -> ScrapeResult | None:
    cached = await cache_get(_cache_key(url_hash))
    if not cached:
        return None
    data = loads_json(cached)
    result = ScrapeResult(**data)
    result.cache_hit = True
    return result


async def _write_cache(url_hash: str, result: ScrapeResult) -> None:
    payload = result.model_dump()
    payload["cache_hit"] = False
    await cache_setex(_cache_key(url_hash), settings.SCRAPING_CACHE_TTL_SECONDS, dumps_json(payload))


async def scrape_once(req: ScrapeRequest) -> ScrapeResult:
    normalized_url = validate_safe_url(req.url)
    domain = _domain(normalized_url)
    url_hash = normalized_hash(normalized_url)
    started_at = time.perf_counter()

    await _enforce_rate_limit(domain)
    await _enforce_client_quota(req.client_id)
    await _check_circuit(domain)

    if not req.force_refresh:
        cached = await _read_cache(url_hash)
        if cached is not None:
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

    lock_ok = await setnx_with_ttl(_inflight_key(url_hash), settings.SCRAPING_DEDUPE_TTL_SECONDS)
    if not lock_ok:
        cached = await _read_cache(url_hash)
        if cached is not None:
            return cached
        raise HTTPException(status_code=409, detail="Duplicate scrape in progress")

    last_exc: Exception | None = None
    for attempt in range(1, settings.SCRAPING_RETRY_MAX_ATTEMPTS + 1):
        try:
            status_code, content_type, body, fetched_via = await fetch_url(normalized_url, render_js=req.render_js)
            result = ScrapeResult(
                url=req.url,
                normalized_url=normalized_url,
                domain=domain,
                status_code=status_code,
                content_type=content_type,
                body=body,
                fetched_via=fetched_via,
                cache_hit=False,
            )
            await _write_cache(url_hash, result)
            await _record_success(domain)
            SCRAPE_REQUESTS_TOTAL.labels(mode=req.mode, outcome="success", domain=domain).inc()
            SCRAPE_LATENCY_SECONDS.labels(mode=req.mode, source=result.fetched_via, domain=domain).observe(
                time.perf_counter() - started_at
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
            )
            return result
        except HTTPException:
            await _record_failure(domain)
            SCRAPE_REQUESTS_TOTAL.labels(mode=req.mode, outcome="http_error", domain=domain).inc()
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await _record_failure(domain)
            if attempt == settings.SCRAPING_RETRY_MAX_ATTEMPTS:
                break
            backoff = (settings.SCRAPING_RETRY_BACKOFF_BASE_MS / 1000.0) * (2 ** (attempt - 1))
            await asyncio.sleep(backoff + random.uniform(0, backoff / 2))

    SCRAPE_REQUESTS_TOTAL.labels(mode=req.mode, outcome="failed", domain=domain).inc()
    logger.exception("scrape_failed", extra={"url": req.url, "domain": domain})
    raise HTTPException(status_code=502, detail=f"Scrape failed: {type(last_exc).__name__}")


async def enqueue_scrape(req: ScrapeRequest) -> ScrapeJobEnqueueResponse:
    normalized_url = validate_safe_url(req.url)
    domain = _domain(normalized_url)
    url_hash = normalized_hash(normalized_url)
    await _enforce_rate_limit(domain)
    await _enforce_client_quota(req.client_id)
    await _check_circuit(domain)

    if not req.force_refresh:
        existing_job_id = await get_dedupe_job(url_hash)
        if existing_job_id:
            existing = await get_job_state(existing_job_id)
            if existing and existing.get("status") in {"queued", "processing"}:
                _log_scrape_event(
                    "scrape_job_deduped",
                    url=req.url,
                    normalized_url=normalized_url,
                    domain=domain,
                    job_id=existing_job_id,
                )
                return ScrapeJobEnqueueResponse(job_id=existing_job_id, status=existing["status"], queued=True)

    depth = await queue_depth()
    SCRAPE_QUEUE_DEPTH.set(depth)
    if depth >= settings.SCRAPING_QUEUE_MAX_DEPTH:
        raise HTTPException(status_code=503, detail="Scrape queue is full")

    job_id = str(uuid.uuid4())
    now = int(time.time())
    state = ScrapeJobState(
        job_id=job_id,
        status="queued",
        created_at=now,
        updated_at=now,
        attempts=0,
        normalized_url=normalized_url,
        result=None,
        error=None,
    )
    payload = {
        "job_id": state.job_id,
        "status": state.status,
        "created_at": str(state.created_at),
        "updated_at": str(state.updated_at),
        "attempts": str(state.attempts),
        "normalized_url": state.normalized_url,
        "request": req.model_dump_json(),
        "result": "",
        "error": "",
    }
    await set_job_state(job_id, payload, settings.SCRAPING_JOB_TTL_SECONDS)
    await set_dedupe_job(url_hash, job_id, settings.SCRAPING_JOB_TTL_SECONDS)
    await enqueue_job(job_id)
    SCRAPE_QUEUE_DEPTH.set(depth + 1)
    _log_scrape_event(
        "scrape_job_enqueued",
        url=req.url,
        normalized_url=normalized_url,
        domain=domain,
        job_id=job_id,
        queue_depth=depth + 1,
    )
    return ScrapeJobEnqueueResponse(job_id=job_id, status="queued", queued=True)


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
    url_hash = normalized_hash(raw.get("normalized_url", req.url))

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
        await clear_dedupe_job(url_hash, job_id)
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
        await clear_dedupe_job(url_hash, job_id)
