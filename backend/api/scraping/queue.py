from __future__ import annotations

import time
import uuid

from fastapi import HTTPException

from api.config import settings
from api.scraping.metrics import SCRAPE_QUEUE_DEPTH
from api.scraping.models import ScrapeJobEnqueueResponse, ScrapeJobState, ScrapeRequest
from api.scraping.security import normalized_hash
from api.scraping.store import (
    clear_dedupe_job,
    decr_with_floor,
    enqueue_job,
    get_dedupe_job,
    get_job_state,
    incr_with_ttl,
    queue_depth,
    set_dedupe_job,
    set_job_state,
)


def client_quota_key(client_id: str, epoch_day: int) -> str:
    return f"scrape:quota:{client_id}:{epoch_day}"


def domain_limit_key(domain: str) -> str:
    return f"scrape:rl:domain:{domain}"


def client_queue_key(client_id: str) -> str:
    return f"scrape:qclient:{client_id}"


def build_job_id(normalized_url: str, *, render_js: bool) -> str:
    return normalized_hash(f"{normalized_url}|render_js={int(render_js)}")


async def find_active_job(url_hash: str) -> dict[str, str] | None:
    existing_job_id = await get_dedupe_job(url_hash)
    if not existing_job_id:
        return None
    existing = await get_job_state(existing_job_id)
    if not existing:
        return None
    if existing.get("status") not in {"queued", "processing"}:
        return None
    return existing


async def ensure_queue_capacity() -> int:
    depth = await queue_depth()
    SCRAPE_QUEUE_DEPTH.set(depth)
    if depth >= settings.SCRAPING_QUEUE_MAX_DEPTH:
        raise HTTPException(status_code=503, detail="Scrape queue is full")
    return depth


async def reserve_client_queue_slot(client_id: str | None) -> None:
    if settings.SCRAPING_CLIENT_MAX_QUEUED_JOBS <= 0 or not client_id:
        return
    key = client_queue_key(client_id)
    count = await incr_with_ttl(key, settings.SCRAPING_JOB_TTL_SECONDS)
    if count > settings.SCRAPING_CLIENT_MAX_QUEUED_JOBS:
        await decr_with_floor(key)
        raise HTTPException(status_code=429, detail="Client queued scrape limit exceeded")


async def release_client_queue_slot(client_id: str | None) -> None:
    if settings.SCRAPING_CLIENT_MAX_QUEUED_JOBS <= 0 or not client_id:
        return
    await decr_with_floor(client_queue_key(client_id))


async def enqueue_request(req: ScrapeRequest, *, normalized_url: str, url_hash: str) -> ScrapeJobEnqueueResponse:
    await reserve_client_queue_slot(req.client_id)
    depth = await ensure_queue_capacity()
    try:
        job_id = str(uuid.uuid4()) if req.force_refresh else build_job_id(normalized_url, render_js=req.render_js)
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
        return ScrapeJobEnqueueResponse(job_id=job_id, status="queued", queued=True)
    except Exception:
        await release_client_queue_slot(req.client_id)
        raise


async def clear_job(url_hash: str, job_id: str | None = None) -> None:
    await clear_dedupe_job(url_hash, job_id)

