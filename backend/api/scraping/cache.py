from __future__ import annotations

import time

from api.config import settings
from api.scraping.models import ScrapeResult
from api.scraping.store import cache_get, cache_setex, delete_key, dumps_json, loads_json, setnx_with_ttl


def cache_key(url_hash: str) -> str:
    return f"scrape:cache:{url_hash}"


def inflight_key(url_hash: str) -> str:
    return f"scrape:inflight:{url_hash}"


async def read_cached_result(url_hash: str, *, allow_stale: bool = False) -> ScrapeResult | None:
    cached = await cache_get(cache_key(url_hash))
    if not cached:
        return None
    payload = loads_json(cached)
    now = int(time.time())
    fresh_until = int(payload.pop("_fresh_until", 0))
    stale_until = int(payload.pop("_stale_until", 0))
    if fresh_until and now > fresh_until and not allow_stale:
        return None
    if stale_until and now > stale_until:
        return None
    result = ScrapeResult(**payload)
    result.cache_hit = True
    result.stale = bool(fresh_until and now > fresh_until)
    return result


async def write_cached_result(url_hash: str, result: ScrapeResult) -> None:
    payload = result.model_dump()
    payload["cache_hit"] = False
    payload["stale"] = False
    now = int(time.time())
    payload["_fresh_until"] = now + settings.SCRAPING_CACHE_TTL_SECONDS
    payload["_stale_until"] = now + max(settings.SCRAPING_CACHE_STALE_TTL_SECONDS, settings.SCRAPING_CACHE_TTL_SECONDS)
    await cache_setex(
        cache_key(url_hash),
        max(settings.SCRAPING_CACHE_STALE_TTL_SECONDS, settings.SCRAPING_CACHE_TTL_SECONDS),
        dumps_json(payload),
    )


async def acquire_inflight_lock(url_hash: str) -> bool:
    return await setnx_with_ttl(inflight_key(url_hash), settings.SCRAPING_DEDUPE_TTL_SECONDS)


async def release_inflight_lock(url_hash: str) -> None:
    await delete_key(inflight_key(url_hash))
