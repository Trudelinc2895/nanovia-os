"""backend/api/scraping/stealth/__init__.py — Stealth scraping package."""
from __future__ import annotations

from api.scraping.stealth.headers import build_stealth_headers
from api.scraping.stealth.fingerprint import apply_stealth_patches
from api.scraping.stealth.behavior import human_jitter, simulate_scroll, wait_for_content
from api.scraping.stealth.proxy_pool import get_proxy, mark_proxy_dead, ProxyPool

__all__ = [
    "build_stealth_headers",
    "apply_stealth_patches",
    "human_jitter",
    "simulate_scroll",
    "wait_for_content",
    "get_proxy",
    "mark_proxy_dead",
    "ProxyPool",
]
