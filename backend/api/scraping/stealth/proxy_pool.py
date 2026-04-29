"""backend/api/scraping/stealth/proxy_pool.py — Advanced proxy management with health checks."""
from __future__ import annotations

import time
from typing import Optional


class ProxyPool:
    """Round-robin proxy pool with dead-proxy detection and automatic recovery."""

    _DEAD_TTL_SECONDS: int = 300  # 5 minutes

    def __init__(self, proxy_list: list[str]) -> None:
        self._proxies: list[str] = list(proxy_list)
        self._dead: dict[str, float] = {}  # proxy → expiry timestamp
        self._index: int = 0

    async def get_proxy(self) -> Optional[str]:
        """Return the next healthy proxy in round-robin order, or None if all are dead."""
        if not self._proxies:
            return None
        now = time.time()
        # Expire dead-proxy records whose TTL has passed
        self._dead = {p: t for p, t in self._dead.items() if t > now}
        healthy = [p for p in self._proxies if p not in self._dead]
        if not healthy:
            return None  # All proxies dead — fall back to direct
        proxy = healthy[self._index % len(healthy)]
        self._index = (self._index + 1) % len(healthy)
        return proxy

    async def mark_dead(self, proxy: str) -> None:
        """Blacklist a proxy for _DEAD_TTL_SECONDS seconds."""
        self._dead[proxy] = time.time() + self._DEAD_TTL_SECONDS

    async def health_check_all(self) -> None:
        """Check each proxy by GETting httpbin.org/ip.  Resurrect recovered proxies."""
        import httpx
        for proxy in list(self._proxies):
            try:
                async with httpx.AsyncClient(proxy=proxy, timeout=5.0) as client:
                    resp = await client.get("http://httpbin.org/ip")
                    if resp.status_code == 200 and proxy in self._dead:
                        del self._dead[proxy]
            except Exception:
                await self.mark_dead(proxy)


# Module-level singleton — lazy-initialised from settings on first use
_pool_instance: Optional[ProxyPool] = None


def _get_pool() -> Optional[ProxyPool]:
    global _pool_instance
    if _pool_instance is None:
        from api.config import settings
        proxies = settings.SCRAPING_PROXY_LIST
        if proxies:
            _pool_instance = ProxyPool(proxies)
    return _pool_instance


async def get_proxy() -> Optional[str]:
    """Return next healthy proxy, or None (falls back to direct connection)."""
    pool = _get_pool()
    if pool is None:
        return None
    return await pool.get_proxy()


async def mark_proxy_dead(proxy: str) -> None:
    """Mark a proxy as dead in the module-level pool."""
    pool = _get_pool()
    if pool is not None:
        await pool.mark_dead(proxy)
