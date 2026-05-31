from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlsplit

from fastapi import HTTPException

from api.config import settings
from api.scraping.fetcher_http import fetch_http
from api.scraping.security import validate_safe_url

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover
    async_playwright = None

_BOT_DETECTION_KEYWORDS = (
    "captcha",
    "challenge",
    "verify you are human",
    "cf-browser-verification",
    "cloudflare ray id",
    "please verify you",
    "attention required",
    "ddos-guard",
    "just a moment",
)


def check_content_safety(html: str, url: str) -> bool:
    lower = html.lower()
    for keyword in _BOT_DETECTION_KEYWORDS:
        if keyword in lower:
            logger.warning("[fetcher_browser] bot_detection url=%s keyword=%r", url, keyword)
            return False
    return True


class BrowserPool:
    def __init__(self, size: int) -> None:
        self._sem = asyncio.Semaphore(size)
        self._pw = None
        self._browser = None
        self._last_used: float = 0.0
        self._zombie_task: asyncio.Task | None = None

    async def _ensure_browser(self):
        if async_playwright is None:
            raise HTTPException(status_code=503, detail="Playwright not installed")
        if self._browser is None:
            self._pw = await asyncio.wait_for(async_playwright().start(), timeout=30)
            self._browser = await asyncio.wait_for(self._pw.chromium.launch(headless=True), timeout=30)
        return self._browser

    async def _close_browser(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        except Exception:
            pass
        finally:
            self._browser = None
        try:
            if self._pw is not None:
                await self._pw.stop()
        except Exception:
            pass
        finally:
            self._pw = None

    async def _zombie_killer(self) -> None:
        while True:
            try:
                await asyncio.sleep(300)
                if self._browser is not None:
                    idle_seconds = time.monotonic() - self._last_used
                    if idle_seconds > 600:
                        logger.info("[fetcher_browser] closing idle browser idle=%.0fs", idle_seconds)
                        await self._close_browser()
            except asyncio.CancelledError:
                logger.info("[fetcher_browser] zombie_killer cancelled")
                return
            except Exception as exc:
                logger.warning("[fetcher_browser] zombie_killer error: %s", exc)

    def start_zombie_killer(self) -> asyncio.Task:
        if self._zombie_task is not None and not self._zombie_task.done():
            return self._zombie_task
        self._zombie_task = asyncio.create_task(self._zombie_killer(), name="playwright_zombie_killer")
        return self._zombie_task

    async def shutdown(self) -> None:
        zombie_task = self._zombie_task
        self._zombie_task = None
        if zombie_task is not None:
            zombie_task.cancel()
            try:
                await zombie_task
            except asyncio.CancelledError:
                pass
        await self._close_browser()

    @asynccontextmanager
    async def page(self) -> AsyncIterator:
        async with self._sem:
            browser = await self._ensure_browser()
            context = await asyncio.wait_for(browser.new_context(), timeout=30)
            page = await asyncio.wait_for(context.new_page(), timeout=15)
            self._last_used = time.monotonic()
            try:
                yield page
            finally:
                self._last_used = time.monotonic()
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await context.close()
                except Exception:
                    pass


_browser_pool = BrowserPool(settings.SCRAPING_BROWSER_POOL_SIZE)


async def fetch_browser(
    normalized_url: str,
    *,
    proxy: str | None,
    request_headers: dict[str, str],
) -> tuple[int, str, str, str, int, bool]:
    if proxy:
        logger.warning("playwright_proxy_fallback_http")
        status_code, content_type, body, redirect_count, used_proxy = await fetch_http(
            normalized_url,
            proxy=proxy,
            request_headers=request_headers,
        )
        return status_code, content_type, body, "http", redirect_count, used_proxy

    async with _browser_pool.page() as page:
        if settings.SCRAPING_STEALTH_MODE:
            from api.scraping.stealth.fingerprint import apply_stealth_patches

            await apply_stealth_patches(page)

        response = await page.goto(
            normalized_url,
            wait_until="domcontentloaded",
            timeout=int(settings.SCRAPING_TIMEOUT_SECONDS * 1000),
        )
        final_url = page.url
        safe_final = validate_safe_url(final_url)
        if urlsplit(safe_final).hostname != urlsplit(final_url).hostname:
            raise HTTPException(status_code=403, detail="Redirect target blocked")

        if settings.SCRAPING_STEALTH_MODE and settings.SCRAPING_STEALTH_SCROLL_SIMULATE:
            from api.scraping.stealth.behavior import simulate_scroll

            await simulate_scroll(page)

        html = await page.content()
        if not check_content_safety(html, normalized_url):
            raise HTTPException(status_code=403, detail="Bot detection page - request blocked")

        body_bytes = html.encode("utf-8", errors="replace")
        if len(body_bytes) > settings.SCRAPING_MAX_RESPONSE_BYTES:
            raise HTTPException(status_code=413, detail="Response too large")

        status_code = 200 if response is None else response.status
        redirect_count = 0 if final_url == normalized_url else 1
        return status_code, "text/html", html, "playwright", redirect_count, False

