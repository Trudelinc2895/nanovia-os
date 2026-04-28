from __future__ import annotations

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from api.config import settings
from api.scraping.security import validate_redirect, validate_safe_url

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover
    async_playwright = None


class BrowserPool:
    def __init__(self, size: int) -> None:
        self._sem = asyncio.Semaphore(size)
        self._pw = None
        self._browser = None

    async def _ensure_browser(self):
        if async_playwright is None:
            raise HTTPException(status_code=503, detail="Playwright not installed")
        if self._browser is None:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
        return self._browser

    @asynccontextmanager
    async def page(self) -> AsyncIterator:
        async with self._sem:
            browser = await self._ensure_browser()
            page = await browser.new_page()
            try:
                yield page
            finally:
                await page.close()


_browser_pool = BrowserPool(settings.SCRAPING_BROWSER_POOL_SIZE)


def _choose_proxy() -> str | None:
    if not settings.SCRAPING_PROXY_ROTATION_ENABLED:
        return None
    proxies = settings.SCRAPING_PROXY_LIST
    if not proxies:
        return None
    return random.choice(proxies)


async def _sleep_jitter() -> None:
    if settings.SCRAPING_JITTER_MAX_MS <= 0:
        return
    ms = random.randint(settings.SCRAPING_JITTER_MIN_MS, settings.SCRAPING_JITTER_MAX_MS)
    await asyncio.sleep(ms / 1000.0)


def _validate_content_type(content_type_header: str) -> str:
    header = (content_type_header or "").split(";", 1)[0].strip().lower()
    if not header:
        raise HTTPException(status_code=415, detail="Missing content-type")
    if header not in settings.SCRAPING_ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported content-type: {header}")
    return header


async def _fetch_http(normalized_url: str) -> tuple[int, str, str]:
    timeout = httpx.Timeout(settings.SCRAPING_TIMEOUT_SECONDS)
    proxy = _choose_proxy()
    current_url = normalized_url

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, proxy=proxy) as client:
        for _ in range(settings.SCRAPING_MAX_REDIRECTS + 1):
            response = await client.get(current_url, headers={"User-Agent": "kt-scraper/1.0"})
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                if not location:
                    raise HTTPException(status_code=502, detail="Redirect without location")
                current_url = validate_redirect(current_url, location)
                continue

            content_type = _validate_content_type(response.headers.get("content-type", ""))
            body_bytes = response.content
            if len(body_bytes) > settings.SCRAPING_MAX_RESPONSE_BYTES:
                raise HTTPException(status_code=413, detail="Response too large")
            await _sleep_jitter()
            return response.status_code, content_type, body_bytes.decode("utf-8", errors="replace")

    raise HTTPException(status_code=508, detail="Too many redirects")


async def _fetch_playwright(normalized_url: str) -> tuple[int, str, str]:
    await _sleep_jitter()
    proxy = _choose_proxy()
    if proxy:
        logger.warning("Proxy rotation with Playwright uses HTTP path fallback for this request")
        return await _fetch_http(normalized_url)

    async with _browser_pool.page() as page:
        response = await page.goto(
            normalized_url,
            wait_until="domcontentloaded",
            timeout=int(settings.SCRAPING_TIMEOUT_SECONDS * 1000),
        )
        final_url = page.url
        safe_final = validate_safe_url(final_url)
        if urlsplit(safe_final).hostname != urlsplit(final_url).hostname:
            raise HTTPException(status_code=403, detail="Redirect target blocked")

        html = await page.content()
        body_bytes = html.encode("utf-8", errors="replace")
        if len(body_bytes) > settings.SCRAPING_MAX_RESPONSE_BYTES:
            raise HTTPException(status_code=413, detail="Response too large")

        status_code = 200 if response is None else response.status
        return status_code, "text/html", html


async def fetch_url(normalized_url: str, *, render_js: bool) -> tuple[int, str, str, str]:
    if render_js:
        code, content_type, body = await _fetch_playwright(normalized_url)
        return code, content_type, body, "playwright"

    code, content_type, body = await _fetch_http(normalized_url)
    return code, content_type, body, "http"
