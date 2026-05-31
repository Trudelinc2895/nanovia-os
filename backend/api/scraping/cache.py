from __future__ import annotations

from api.config import settings
from api.scraping.models import ScrapeResult
from api.scraping.store import cache_get, cache_setex, dumps_json, loads_json, setnx_with_ttl


def cache_key(url_hash: str) -> str:
    return f"scrape:cache:{url_hash}"


def inflight_key(url_hash: str) -> str:
    return f"scrape:inflight:{url_hash}"


async def read_cached_result(url_hash: str) -> ScrapeResult | None:
    cached = await cache_get(cache_key(url_hash))
    if not cached:
        return None
    result = ScrapeResult(**loads_json(cached))
    result.cache_hit = True
    return result


async def write_cached_result(url_hash: str, result: ScrapeResult) -> None:
    payload = result.model_dump()
    payload["cache_hit"] = False
    await cache_setex(cache_key(url_hash), settings.SCRAPING_CACHE_TTL_SECONDS, dumps_json(payload))


async def acquire_inflight_lock(url_hash: str) -> bool:
    return await setnx_with_ttl(inflight_key(url_hash), settings.SCRAPING_DEDUPE_TTL_SECONDS)

