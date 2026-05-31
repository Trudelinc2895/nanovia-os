from __future__ import annotations

import asyncio
import random
from urllib.parse import urlsplit

from api.config import settings
from api.scraping.feature_flags import browser_rendering_enabled
from api.scraping.fetcher_browser import _browser_pool, fetch_browser
from api.scraping.fetcher_http import fetch_http
from api.scraping.proxy_manager import choose_proxy, choose_proxy_stealth, mark_proxy_dead


async def _sleep_jitter() -> None:
    if settings.SCRAPING_JITTER_MAX_MS <= 0:
        return
    if settings.SCRAPING_STEALTH_MODE:
        from api.scraping.stealth.behavior import human_jitter

        await human_jitter(settings.SCRAPING_JITTER_MIN_MS, settings.SCRAPING_JITTER_MAX_MS)
    else:
        ms = random.randint(settings.SCRAPING_JITTER_MIN_MS, settings.SCRAPING_JITTER_MAX_MS)
        await asyncio.sleep(ms / 1000.0)


async def fetch_url(normalized_url: str, *, render_js: bool) -> tuple[int, str, str, str, int, bool]:
    domain = (urlsplit(normalized_url).hostname or "").lower()
    if settings.SCRAPING_STEALTH_MODE and settings.SCRAPING_PROXY_ROTATION_ENABLED:
        proxy = await choose_proxy_stealth(domain)
    else:
        proxy = choose_proxy(domain)

    if settings.SCRAPING_STEALTH_MODE and settings.SCRAPING_STEALTH_HEADER_ROTATION:
        from api.scraping.stealth.headers import build_stealth_headers

        req_headers = build_stealth_headers()
    else:
        req_headers = {"User-Agent": settings.SCRAPING_USER_AGENT}

    try:
        await _sleep_jitter()
        if render_js and browser_rendering_enabled():
            return await fetch_browser(normalized_url, proxy=proxy, request_headers=req_headers)
        status_code, content_type, body, redirect_count, used_proxy = await fetch_http(
            normalized_url,
            proxy=proxy,
            request_headers=req_headers,
        )
        return status_code, content_type, body, "http", redirect_count, used_proxy
    except Exception:
        if settings.SCRAPING_STEALTH_MODE and proxy:
            await mark_proxy_dead(proxy)
        raise

