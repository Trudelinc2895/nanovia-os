from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass

import redis.asyncio as aioredis

from api.config import settings


@dataclass
class _LocalValue:
    expires_at: float
    value: str


_local_cache: dict[str, _LocalValue] = {}
_local_locks: dict[str, float] = {}
_local_circuit: dict[str, dict[str, float]] = {}
_local_jobs: dict[str, dict[str, str]] = {}
_local_job_dedupe: dict[str, _LocalValue] = {}
_local_queue: deque[str] = deque()

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    return _redis_pool


def _now() -> float:
    return time.time()


def _prune_local_cache() -> None:
    now = _now()
    stale = [key for key, val in _local_cache.items() if val.expires_at <= now]
    for key in stale:
        _local_cache.pop(key, None)


def _prune_local_job_dedupe() -> None:
    now = _now()
    stale = [key for key, val in _local_job_dedupe.items() if val.expires_at <= now]
    for key in stale:
        _local_job_dedupe.pop(key, None)


async def cache_get(key: str) -> str | None:
    try:
        redis = await get_redis()
        return await redis.get(key)
    except Exception:
        _prune_local_cache()
        item = _local_cache.get(key)
        if not item:
            return None
        return item.value


async def cache_setex(key: str, ttl: int, value: str) -> None:
    try:
        redis = await get_redis()
        await redis.setex(key, ttl, value)
    except Exception:
        _local_cache[key] = _LocalValue(expires_at=_now() + ttl, value=value)


async def setnx_with_ttl(key: str, ttl: int) -> bool:
    try:
        redis = await get_redis()
        return bool(await redis.set(key, "1", ex=ttl, nx=True))
    except Exception:
        now = _now()
        expiry = _local_locks.get(key, 0)
        if expiry > now:
            return False
        _local_locks[key] = now + ttl
        return True


async def incr_with_ttl(key: str, ttl: int) -> int:
    try:
        redis = await get_redis()
        count = int(await redis.incr(key))
        if count == 1:
            await redis.expire(key, ttl)
        return count
    except Exception:
        _prune_local_cache()
        item = _local_cache.get(key)
        if not item:
            count = 1
        else:
            try:
                count = int(item.value) + 1
            except Exception:
                count = 1
        _local_cache[key] = _LocalValue(expires_at=_now() + ttl, value=str(count))
        return count


async def circuit_get(domain: str) -> dict[str, int]:
    key = f"scrape:circuit:{domain}"
    now = int(_now())
    try:
        redis = await get_redis()
        raw = await redis.hgetall(key)
        if not raw:
            return {"failures": 0, "opened_until": 0}
        return {
            "failures": int(raw.get("failures", "0")),
            "opened_until": int(raw.get("opened_until", "0")),
        }
    except Exception:
        current = _local_circuit.get(domain, {"failures": 0, "opened_until": 0})
        if int(current.get("opened_until", 0)) < now and int(current.get("failures", 0)) > 0:
            current = {"failures": 0, "opened_until": 0}
            _local_circuit[domain] = current
        return {"failures": int(current.get("failures", 0)), "opened_until": int(current.get("opened_until", 0))}


async def circuit_set(domain: str, failures: int, opened_until: int, ttl: int) -> None:
    key = f"scrape:circuit:{domain}"
    mapping = {"failures": str(failures), "opened_until": str(opened_until)}
    try:
        redis = await get_redis()
        await redis.hset(key, mapping=mapping)
        await redis.expire(key, ttl)
    except Exception:
        _local_circuit[domain] = {"failures": failures, "opened_until": opened_until}


async def queue_depth() -> int:
    try:
        redis = await get_redis()
        return int(await redis.llen("scrape:queue"))
    except Exception:
        return len(_local_queue)


async def enqueue_job(job_id: str) -> None:
    try:
        redis = await get_redis()
        await redis.lpush("scrape:queue", job_id)
    except Exception:
        _local_queue.appendleft(job_id)


async def dequeue_job(timeout_seconds: int = 5) -> str | None:
    try:
        redis = await get_redis()
        row = await redis.brpop("scrape:queue", timeout=timeout_seconds)
        if not row:
            return None
        return row[1]
    except Exception:
        if not _local_queue:
            return None
        return _local_queue.pop()


async def set_job_state(job_id: str, payload: dict[str, str], ttl: int) -> None:
    key = f"scrape:job:{job_id}"
    try:
        redis = await get_redis()
        await redis.hset(key, mapping=payload)
        await redis.expire(key, ttl)
    except Exception:
        _local_jobs[job_id] = payload


async def get_job_state(job_id: str) -> dict[str, str] | None:
    key = f"scrape:job:{job_id}"
    try:
        redis = await get_redis()
        raw = await redis.hgetall(key)
        return raw or None
    except Exception:
        return _local_jobs.get(job_id)


async def get_dedupe_job(url_hash: str) -> str | None:
    key = f"scrape:jobdedupe:{url_hash}"
    try:
        redis = await get_redis()
        return await redis.get(key)
    except Exception:
        _prune_local_job_dedupe()
        item = _local_job_dedupe.get(key)
        return None if item is None else item.value


async def set_dedupe_job(url_hash: str, job_id: str, ttl: int) -> None:
    key = f"scrape:jobdedupe:{url_hash}"
    try:
        redis = await get_redis()
        await redis.setex(key, ttl, job_id)
    except Exception:
        _local_job_dedupe[key] = _LocalValue(expires_at=_now() + ttl, value=job_id)


async def clear_dedupe_job(url_hash: str, job_id: str | None = None) -> None:
    key = f"scrape:jobdedupe:{url_hash}"
    try:
        redis = await get_redis()
        if job_id is not None:
            current = await redis.get(key)
            if current and current != job_id:
                return
        await redis.delete(key)
    except Exception:
        _prune_local_job_dedupe()
        current = _local_job_dedupe.get(key)
        if current is None:
            return
        if job_id is not None and current.value != job_id:
            return
        _local_job_dedupe.pop(key, None)


def dumps_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def loads_json(value: str) -> dict:
    return json.loads(value)
