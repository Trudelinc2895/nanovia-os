from __future__ import annotations

import hashlib
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

from fastapi import HTTPException

from api.config import settings


_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}


def normalize_url(raw_url: str) -> str:
    value = (raw_url or "").strip()
    parsed = urlsplit(value)

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http(s) URLs are allowed")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL host is required")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URL credentials are not allowed")

    host = parsed.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS:
        raise HTTPException(status_code=403, detail="Host blocked")

    port = parsed.port
    netloc = host
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"

    path = parsed.path or "/"
    return urlunsplit((parsed.scheme, netloc, path, parsed.query, ""))


def normalized_hash(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def _is_blocked_ip(ip_str: str) -> bool:
    ip_obj = ipaddress.ip_address(ip_str)
    return any(
        (
            ip_obj.is_private,
            ip_obj.is_loopback,
            ip_obj.is_link_local,
            ip_obj.is_reserved,
            ip_obj.is_multicast,
            ip_obj.is_unspecified,
        )
    )


def validate_allowlist(hostname: str) -> None:
    allowlist = settings.SCRAPING_ALLOWLIST
    host = hostname.lower().rstrip(".")

    if settings.SCRAPING_STRICT_ALLOWLIST and not allowlist:
        raise HTTPException(status_code=503, detail="Scraping allowlist is not configured")

    if allowlist:
        allowed = any(host == domain or host.endswith(f".{domain}") for domain in allowlist)
        if not allowed:
            raise HTTPException(status_code=403, detail="Domain not allowed")


def validate_dns_and_ip(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail="Host resolution failed") from exc

    seen: set[str] = set()
    for info in infos:
        ip_str = info[4][0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        if _is_blocked_ip(ip_str):
            raise HTTPException(status_code=403, detail="Resolved IP blocked by SSRF policy")


def validate_safe_url(raw_url: str) -> str:
    normalized = normalize_url(raw_url)
    host = urlsplit(normalized).hostname
    if not host:
        raise HTTPException(status_code=400, detail="Invalid host")
    validate_allowlist(host)
    validate_dns_and_ip(host)
    return normalized


def validate_redirect(base_url: str, location: str) -> str:
    next_url = urljoin(base_url, location)
    return validate_safe_url(next_url)
