from __future__ import annotations

import hashlib
import logging

from api.scraping import feature_flags
from api.config import settings

logger = logging.getLogger(__name__)


def should_bypass_proxy(domain: str) -> bool:
    host = (domain or "").lower().rstrip(".")
    bypass_domains = settings.SCRAPING_PROXY_BYPASS_DOMAINS
    return any(host == item or host.endswith(f".{item}") for item in bypass_domains)


def choose_proxy(domain: str) -> str | None:
    if not feature_flags.proxy_rotation_enabled():
        return None
    if should_bypass_proxy(domain):
        return None

    proxies = settings.SCRAPING_PROXY_LIST
    if not proxies:
        return None

    digest = hashlib.sha256(domain.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], byteorder="big") % len(proxies)
    return proxies[index]


async def choose_proxy_stealth(domain: str) -> str | None:
    if not feature_flags.proxy_rotation_enabled():
        return None
    if should_bypass_proxy(domain):
        return None

    from api.scraping.stealth.proxy_pool import get_proxy

    return await get_proxy()


async def mark_proxy_dead(proxy: str | None) -> None:
    if not proxy:
        return
    try:
        from api.scraping.stealth.proxy_pool import mark_proxy_dead as _mark_proxy_dead

        await _mark_proxy_dead(proxy)
    except Exception:
        logger.warning("scraping_proxy_mark_dead_failed", extra={"proxy": proxy})

