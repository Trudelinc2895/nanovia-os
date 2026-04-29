"""backend/api/scraping/stealth/headers.py — Coherent browser fingerprint headers.

Profiles:
  - Chrome 124 on Windows
  - Chrome 123 on macOS
  - Firefox 125 on Linux
"""
from __future__ import annotations

import random
from typing import Optional

_PROFILES: list[dict[str, str]] = [
    {
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "accept_language": "en-US,en;q=0.9",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"Windows"',
        "platform": "Win32",
    },
    {
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "accept_language": "en-US,en;q=0.9",
        "sec_ch_ua": '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"macOS"',
        "platform": "MacIntel",
    },
    {
        "ua": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "accept_language": "en-US,en;q=0.5",
        "sec_ch_ua": "",
        "sec_ch_ua_platform": "",
        "platform": "Linux x86_64",
    },
]


def build_stealth_headers(profile: Optional[dict] = None) -> dict[str, str]:
    """Return coherent browser fingerprint headers for stealth HTTP requests.

    Args:
        profile: Override profile dict.  If None, a random profile is chosen.

    Returns:
        Mapping of header name → value.  All headers are internally consistent
        (User-Agent matches Sec-CH-UA, Accept-Language, etc.).
    """
    p = profile if profile is not None else random.choice(_PROFILES)
    headers: dict[str, str] = {
        "User-Agent": p["ua"],
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": p["accept_language"],
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
    }
    if p.get("sec_ch_ua"):
        headers["Sec-CH-UA"] = p["sec_ch_ua"]
        headers["Sec-CH-UA-Mobile"] = "?0"
        headers["Sec-CH-UA-Platform"] = p["sec_ch_ua_platform"]
    return headers
