"""backend/api/scraping/risk.py — URL risk scoring for SSRF and abuse prevention."""
from __future__ import annotations

import ipaddress
import math
from urllib.parse import urlsplit

_SUSPICIOUS_TLDS: frozenset[str] = frozenset({
    ".xyz", ".top", ".tk", ".pw", ".cc", ".info",
})


def _shannon_entropy(s: str) -> float:
    """Compute Shannon entropy of a string (bits per character)."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def score_url(url: str) -> float:
    """Score a URL for risk.  Returns a float in [0.0, 1.0].

    Factors (additive, clamped):
      - IP address as hostname:            +0.8
      - Non-standard port:                 +0.3
      - High-entropy hostname (DGA):       +0.3  (Shannon entropy > 4.0)
      - Suspicious TLD:                    +0.2
      - Short hostname (< 4 chars):        +0.2
      - URL length > 200 chars:            +0.1
      - Many query params (> 5):           +0.1
    """
    try:
        parsed = urlsplit(url)
    except Exception:
        return 1.0

    hostname = (parsed.hostname or "").lower()
    score = 0.0

    # IP address as hostname
    try:
        ipaddress.ip_address(hostname)
        score += 0.8
    except ValueError:
        pass

    # Non-standard port
    port = parsed.port
    if port is not None:
        is_default = (parsed.scheme == "http" and port == 80) or (
            parsed.scheme == "https" and port == 443
        )
        if not is_default:
            score += 0.3

    # High entropy hostname (likely DGA-generated)
    if _shannon_entropy(hostname) > 4.0:
        score += 0.3

    # Suspicious TLD
    for tld in _SUSPICIOUS_TLDS:
        if hostname.endswith(tld):
            score += 0.2
            break

    # Short hostname
    if 0 < len(hostname) < 4:
        score += 0.2

    # Long URL
    if len(url) > 200:
        score += 0.1

    # Many query parameters
    query = parsed.query or ""
    if query:
        param_count = len([p for p in query.split("&") if p])
        if param_count > 5:
            score += 0.1

    return min(1.0, score)


def is_risky(url: str) -> bool:
    """Return True if the URL's risk score meets or exceeds the configured threshold."""
    from api.config import settings
    return score_url(url) >= settings.SCRAPING_RISK_SCORE_THRESHOLD
