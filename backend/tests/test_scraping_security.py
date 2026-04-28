from __future__ import annotations

import socket

import pytest
from fastapi import HTTPException

from api.scraping import security


def test_normalize_url_strips_fragment_and_default_port():
    out = security.normalize_url("https://Example.com:443/path?q=1#frag")
    assert out == "https://example.com/path?q=1"


def test_normalize_url_rejects_non_http_scheme():
    with pytest.raises(HTTPException) as exc:
        security.normalize_url("file:///etc/passwd")
    assert exc.value.status_code == 400


def test_validate_allowlist_blocks_unknown_domain(monkeypatch):
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_STRICT_ALLOWLIST", True)
    monkeypatch.setattr("api.scraping.security.settings.SCRAPING_ALLOWLIST_RAW", "example.com")
    with pytest.raises(HTTPException) as exc:
        security.validate_allowlist("internal.local")
    assert exc.value.status_code == 403


def test_validate_dns_and_ip_blocks_private(monkeypatch):
    def _fake_getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr("api.scraping.security.socket.getaddrinfo", _fake_getaddrinfo)

    with pytest.raises(HTTPException) as exc:
        security.validate_dns_and_ip("localhost")
    assert exc.value.status_code == 403
