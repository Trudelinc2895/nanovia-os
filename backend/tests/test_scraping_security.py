from __future__ import annotations

import socket

import pytest
from fastapi import HTTPException

from api.scraping import security


def test_normalize_url_strips_fragment_and_default_port():
    out = security.normalize_url("https://Example.com:443/path?q=1#frag")
    assert out == "https://example.com/path?q=1"


def test_canonicalize_url_for_cache_removes_tracking_params_and_sorts_query():
    normalized = "https://example.com/path?utm_source=ad&b=2&gclid=123&a=1"
    out = security.canonicalize_url_for_cache(normalized)
    assert out == "https://example.com/path?a=1&b=2"


def test_normalize_url_preserves_path_slash_query_order_and_encoding():
    out = security.normalize_url("https://Example.com:443/path/?b=2&a=1%2B2&a=3+4#frag")
    assert out == "https://example.com/path/?b=2&a=1%2B2&a=3+4"


def test_redact_url_for_logs_strips_query_and_fragment():
    out = security.redact_url_for_logs("https://Example.com:443/path/to?a=secret&b=1#frag")
    assert out == "https://example.com/path/to"


def test_normalize_url_rejects_non_http_scheme():
    with pytest.raises(HTTPException) as exc:
        security.normalize_url("file:///etc/passwd")
    assert exc.value.status_code == 400


def test_normalize_url_blocks_sensitive_ports():
    with pytest.raises(HTTPException) as exc:
        security.normalize_url("https://example.com:22/")
    assert exc.value.status_code == 403


def test_validate_allowlist_blocks_unknown_domain(monkeypatch):
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_STRICT_ALLOWLIST", True)
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_ALLOWLIST_RAW", "example.com")
    with pytest.raises(HTTPException) as exc:
        security.validate_allowlist("internal.local")
    assert exc.value.status_code == 403


def test_validate_dns_and_ip_blocks_private(monkeypatch):
    def _fake_getaddrinfo(host, port, family=0, type=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr("api.scraping.security.socket.getaddrinfo", _fake_getaddrinfo)

    with pytest.raises(HTTPException) as exc:
        security.validate_dns_and_ip("localhost")
    assert exc.value.status_code == 403


def test_validate_dns_and_ip_allows_private_when_flag_disabled(monkeypatch):
    def _fake_getaddrinfo(host, port, family=0, type=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr("api.scraping.security.socket.getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_BLOCK_PRIVATE_IPS", False)

    security.validate_dns_and_ip("localhost")


def test_validate_safe_url_blocks_cloud_metadata_ip(monkeypatch):
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_STRICT_ALLOWLIST", False)

    with pytest.raises(HTTPException) as exc:
        security.validate_safe_url("http://100.100.100.200/latest/meta-data/")

    assert exc.value.status_code == 403


def test_validate_safe_url_blocks_cloud_metadata_hostname(monkeypatch):
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_STRICT_ALLOWLIST", False)

    with pytest.raises(HTTPException) as exc:
        security.validate_safe_url("http://metadata.google.internal/computeMetadata/v1/")

    assert exc.value.status_code == 403


def test_validate_dns_and_ip_checks_a_and_aaaa_records(monkeypatch):
    calls: list[int] = []

    def _fake_getaddrinfo(host, port, family=0, type=0):
        calls.append(family)
        if family == socket.AF_INET:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        if family == socket.AF_INET6:
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 0, 0, 0))]
        return []

    monkeypatch.setattr("api.scraping.security.socket.getaddrinfo", _fake_getaddrinfo)

    security.validate_dns_and_ip("example.com")

    assert calls.count(socket.AF_INET) >= 1
    assert calls.count(socket.AF_INET6) >= 1


def test_validate_dns_and_ip_blocks_dns_rebinding(monkeypatch):
    call_count = {"value": 0}

    def _fake_getaddrinfo(host, port, family=0, type=0):
        call_count["value"] += 1
        if call_count["value"] <= 2:
            if family == socket.AF_INET:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
            return []
        if family == socket.AF_INET:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        return []

    monkeypatch.setattr("api.scraping.security.socket.getaddrinfo", _fake_getaddrinfo)

    with pytest.raises(HTTPException) as exc:
        security.validate_dns_and_ip("rebind.example.com")

    assert exc.value.status_code == 403


def test_validate_redirect_blocks_private_ip_target(monkeypatch):
    def _fake_getaddrinfo(host, port, family=0, type=0):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        if host == "127.0.0.1":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        return []

    monkeypatch.setattr("api.scraping.security.socket.getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_STRICT_ALLOWLIST", False)

    with pytest.raises(HTTPException) as exc:
        security.validate_redirect("https://example.com/start", "http://127.0.0.1/admin")

    assert exc.value.status_code == 403


def test_validate_safe_url_rejects_invalid_url_cleanly(monkeypatch):
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_STRICT_ALLOWLIST", False)

    with pytest.raises(HTTPException) as exc:
        security.validate_safe_url("https:///missing-host")

    assert exc.value.status_code == 400
