"""backend/api/scraping/stealth/behavior.py — Human behavior simulation for stealth scraping."""
from __future__ import annotations

import asyncio
import random


async def human_jitter(min_ms: int, max_ms: int) -> None:
    """Sleep for a Gaussian-distributed duration between min_ms and max_ms.

    Uses a Gaussian distribution (mean=(min+max)/2, sigma=(max-min)/6) clamped
    to [min_ms, max_ms], which is more human-like than uniform random.
    """
    if max_ms <= 0:
        return
    if min_ms >= max_ms:
        await asyncio.sleep(min_ms / 1000.0)
        return
    mean = (min_ms + max_ms) / 2.0
    sigma = max(1.0, (max_ms - min_ms) / 6.0)
    ms = random.gauss(mean, sigma)
    ms = max(float(min_ms), min(float(max_ms), ms))
    await asyncio.sleep(ms / 1000.0)


async def simulate_scroll(page) -> None:
    """Simulate human-like scrolling behaviour on a Playwright page.

    Scrolls the page in 3–5 small steps with random delays between each.
    Each step scrolls between 200 and 800 pixels down.
    """
    steps = random.randint(3, 5)
    for _ in range(steps):
        scroll_amount = random.randint(200, 800)
        try:
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        except Exception:  # pragma: no cover
            pass
        await asyncio.sleep(random.uniform(0.1, 0.4))


async def wait_for_content(page) -> None:
    """Wait for page content to settle.

    Tries network-idle first, falls back to domcontentloaded, then a 500ms
    settle time.
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
    await asyncio.sleep(0.5)
