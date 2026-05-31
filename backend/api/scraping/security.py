from __future__ import annotations

import hashlib
import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from fastapi import HTTPException

from api.config import settings


_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}
_BLOCKED_METADATA_HOSTS = {
    "metadata",
    "metadata.google.internal",
}
_BLOCKED_METADATA_IPS = {
    ipaddress.ip_address("100.100.100.200"),  # Alibaba metadata service
    ipaddress.ip_address("168.63.129.16"),    # Azure WireServer
    ipaddress.ip_address("169.254.169.254"),  # AWS/Azure/GCP metadata service
}
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "ref",
    "ref_src",
    "source",
}
_BLOCKED_PORTS = frozenset(
    {
        21,
        22,
        23,
        25,
        53,
        111,
        135,
        137,
        138,
        139,
        389,
        445,
        1433,
        1521,
        2049,
        2375,
        2376,
        3306,
        3389,
        4369,
        5432,
        5672,
        5985,
        5986,
        6379,
        9200,
        9300,
        11211,
        27017,
    }
)


def _format_netloc(scheme: str, hostname: str, port: int | None) -> str:
    host = hostname.lower().rstrip(".")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        return f"{host}:{port}"
    return host


def _normalize_host(hostname: str) -> str:
    return hostname.lower().rstrip(".")


def _validate_host_policy(hostname: str) -> None:
    host = _normalize_host(hostname)
    if host in _BLOCKED_HOSTS or host in _BLOCKED_METADATA_HOSTS:
        raise HTTPException(status_code=403, detail="Host blocked")


def _validate_port(scheme: str, port: int | None) -> None:
    if port is None:
        return
    if port <= 0 or port > 65535:
        raise HTTPException(status_code=400, detail="URL port is invalid")
    if port in _BLOCKED_PORTS:
        raise HTTPException(status_code=403, detail="URL port blocked by SSRF policy")
    if scheme == "http" and port == 443:
        raise HTTPException(status_code=400, detail="URL port is invalid for http")
    if scheme == "https" and port == 80:
        raise HTTPException(status_code=400, detail="URL port is invalid for https")


def normalize_url(raw_url: str) -> str:
    value = (raw_url or "").strip()
    parsed = urlsplit(value)

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http(s) URLs are allowed")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL host is required")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URL credentials are not allowed")

    host = _normalize_host(parsed.hostname)
    _validate_host_policy(host)
    try:
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="URL port is invalid") from exc
    _validate_port(parsed.scheme, port)

    path = parsed.path or "/"
    netloc = _format_netloc(parsed.scheme, host, port)
    return urlunsplit((parsed.scheme, netloc, path, parsed.query, ""))


def normalized_hash(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def canonicalize_url_for_cache(normalized_url: str) -> str:
    parsed = urlsplit(normalized_url)
    filtered_params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    filtered_params.sort(key=lambda item: (item[0], item[1]))
    canonical_query = urlencode(filtered_params, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", canonical_query, ""))


def request_fingerprint(normalized_url: str, *, render_js: bool) -> str:
    return f"{canonicalize_url_for_cache(normalized_url)}|render_js={int(render_js)}"


def redact_url_for_logs(raw_url: str) -> str:
    value = (raw_url or "").strip()
    if not value:
        return ""

    try:
        parsed = urlsplit(value)
    except Exception:
        return "<invalid-url>"

    if not parsed.scheme or not parsed.hostname:
        return "<invalid-url>"

    netloc = _format_netloc(parsed.scheme, parsed.hostname, parsed.port)
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def _is_blocked_ip(ip_str: str) -> bool:
    ip_obj = ipaddress.ip_address(ip_str)
    if ip_obj in _BLOCKED_METADATA_IPS:
        return True
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


def resolve_dns_records(hostname: str) -> set[str]:
    records: set[str] = set()

    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            infos = socket.getaddrinfo(hostname, None, family, socket.SOCK_STREAM)
        except socket.gaierror:
            continue
        for info in infos:
            ip_str = info[4][0]
            if ip_str:
                records.add(ip_str)

    if not records:
        raise HTTPException(status_code=400, detail="Host resolution failed")
    return records


def validate_allowlist(hostname: str) -> None:
    allowlist = settings.SCRAPING_ALLOWLIST
    host = _normalize_host(hostname)

    if settings.SCRAPING_STRICT_ALLOWLIST and not allowlist:
        raise HTTPException(status_code=503, detail="Scraping allowlist is not configured")

    if allowlist:
        allowed = any(host == domain or host.endswith(f".{domain}") for domain in allowlist)
        if not allowed:
            raise HTTPException(status_code=403, detail="Domain not allowed")


def validate_dns_and_ip(hostname: str) -> None:
    seen = resolve_dns_records(hostname)
    seen |= resolve_dns_records(hostname)
    if not settings.SCRAPING_BLOCK_PRIVATE_IPS:
        return
    for ip_str in seen:
        if _is_blocked_ip(ip_str):
            raise HTTPException(status_code=403, detail="Resolved IP blocked by SSRF policy")


def validate_safe_url(raw_url: str) -> str:
    normalized = normalize_url(raw_url)
    host = urlsplit(normalized).hostname
    if not host:
        raise HTTPException(status_code=400, detail="Invalid host")
    _validate_host_policy(host)
    validate_allowlist(host)
    validate_dns_and_ip(host)
    return normalized


def validate_redirect(base_url: str, location: str) -> str:
    next_url = urljoin(base_url, location)
    validated = validate_safe_url(next_url)
    source_host = urlsplit(base_url).hostname or ""
    target_host = urlsplit(validated).hostname or ""
    if source_host.lower().rstrip(".") != target_host.lower().rstrip("."):
        raise HTTPException(status_code=403, detail="Redirect target blocked")
    return validated
