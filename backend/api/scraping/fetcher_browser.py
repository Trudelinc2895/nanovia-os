from __future__ import annotations

import asyncio
import inspect
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlsplit

from fastapi import HTTPException

from api.config import settings
from api.scraping.fetcher_http import fetch_http
from api.scraping.security import validate_redirect, validate_safe_url

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


def _validate_browser_request_target(previous_url: str, target_url: str, *, initial: bool) -> str:
    if initial:
        return validate_safe_url(target_url)
    return validate_redirect(previous_url, target_url)


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
        except Exception as exc:
            logger.debug("[fetcher_browser] browser close failed: %s", exc)
        finally:
            self._browser = None
        try:
            if self._pw is not None:
                await self._pw.stop()
        except Exception as exc:
            logger.debug("[fetcher_browser] playwright stop failed: %s", exc)
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
    async def page(self, *, context_options: dict[str, object] | None = None) -> AsyncIterator:
        async with self._sem:
            browser = await self._ensure_browser()
            context = await asyncio.wait_for(browser.new_context(**(context_options or {})), timeout=30)
            page = await asyncio.wait_for(context.new_page(), timeout=15)
            self._last_used = time.monotonic()
            try:
                yield page
            finally:
                self._last_used = time.monotonic()
                try:
                    await page.close()
                except Exception as exc:
                    logger.debug("[fetcher_browser] page close failed: %s", exc)
                try:
                    await context.close()
                except Exception as exc:
                    logger.debug("[fetcher_browser] browser context close failed: %s", exc)


_browser_pool = BrowserPool(settings.SCRAPING_BROWSER_POOL_SIZE)


async def fetch_browser(
    normalized_url: str,
    *,
    proxy: str | None,
    request_headers: dict[str, str],
    stealth_profile: dict[str, object] | None = None,
) -> tuple[int, str, str, str, int, bool]:
    if proxy:
        logger.warning("playwright_proxy_fallback_http")
        status_code, content_type, body, redirect_count, used_proxy = await fetch_http(
            normalized_url,
            proxy=proxy,
            request_headers=request_headers,
        )
        return status_code, content_type, body, "http", redirect_count, used_proxy

    context_options: dict[str, object] = {}
    if stealth_profile is not None:
        context_options = {
            "user_agent": str(stealth_profile.get("ua", request_headers.get("User-Agent", settings.SCRAPING_USER_AGENT))),
            "locale": str(stealth_profile.get("locale", settings.SCRAPING_ACCEPT_LANGUAGE.split(",", 1)[0] or "en-US")),
            "timezone_id": settings.SCRAPING_STEALTH_TIMEZONE,
            "viewport": {
                "width": settings.SCRAPING_STEALTH_VIEWPORT_WIDTH,
                "height": settings.SCRAPING_STEALTH_VIEWPORT_HEIGHT,
            },
        }
    else:
        context_options = {
            "user_agent": request_headers.get("User-Agent", settings.SCRAPING_USER_AGENT),
            "locale": settings.SCRAPING_ACCEPT_LANGUAGE.split(",", 1)[0] or "en-US",
            "timezone_id": settings.SCRAPING_STEALTH_TIMEZONE,
            "viewport": {
                "width": settings.SCRAPING_STEALTH_VIEWPORT_WIDTH,
                "height": settings.SCRAPING_STEALTH_VIEWPORT_HEIGHT,
            },
        }

    async with _browser_pool.page(context_options=context_options) as page:
        blocked_navigation: HTTPException | None = None
        allowed_url = normalized_url
        redirect_count = 0
        initial_navigation_pending = True

        async def _guard_navigation(route) -> None:
            nonlocal blocked_navigation, allowed_url, redirect_count, initial_navigation_pending

            request = route.request
            is_navigation_request = False
            request_nav = getattr(request, "is_navigation_request", None)
            if callable(request_nav):
                is_navigation_request = bool(request_nav())
            elif isinstance(request_nav, bool):
                is_navigation_request = request_nav

            request_frame = getattr(request, "frame", None)
            if is_navigation_request and request_frame == getattr(page, "main_frame", None):
                try:
                    validated_target = _validate_browser_request_target(
                        allowed_url,
                        request.url,
                        initial=initial_navigation_pending,
                    )
                except HTTPException as exc:
                    blocked_navigation = exc
                    await route.abort("blockedbyclient")
                    return

                if not initial_navigation_pending and validated_target != allowed_url:
                    redirect_count += 1
                allowed_url = validated_target
                initial_navigation_pending = False

            await route.continue_()

        await page.route("**/*", _guard_navigation)
        if request_headers:
            await page.set_extra_http_headers(request_headers)

        if settings.SCRAPING_STEALTH_MODE:
            from api.scraping.stealth.fingerprint import apply_stealth_patches
            from api.scraping.stealth.behavior import wait_for_content

            await apply_stealth_patches(page, stealth_profile)

        try:
            response = await page.goto(
                normalized_url,
                wait_until="domcontentloaded",
                timeout=int(settings.SCRAPING_TIMEOUT_SECONDS * 1000),
            )
        except Exception:
            if blocked_navigation is not None:
                raise blocked_navigation
            raise
        finally:
            unroute_result = page.unroute("**/*", _guard_navigation)
            if inspect.isawaitable(unroute_result):
                await unroute_result

        if blocked_navigation is not None:
            raise blocked_navigation

        final_url = page.url
        safe_final = validate_safe_url(final_url)
        if urlsplit(safe_final).hostname != urlsplit(allowed_url).hostname:
            raise HTTPException(status_code=403, detail="Redirect target blocked")

        if settings.SCRAPING_STEALTH_MODE and settings.SCRAPING_STEALTH_SCROLL_SIMULATE:
            from api.scraping.stealth.behavior import simulate_scroll

            await simulate_scroll(page)
            await wait_for_content(page)
        elif settings.SCRAPING_STEALTH_MODE:
            from api.scraping.stealth.behavior import wait_for_content

            await wait_for_content(page)

        html = await page.content()
        if not check_content_safety(html, normalized_url):
            raise HTTPException(status_code=403, detail="Bot detection page - request blocked")

        body_bytes = html.encode("utf-8", errors="replace")
        if len(body_bytes) > settings.SCRAPING_MAX_RESPONSE_BYTES:
            raise HTTPException(status_code=413, detail="Response too large")

        status_code = 200 if response is None else response.status
        return status_code, "text/html", html, "playwright", redirect_count, False
