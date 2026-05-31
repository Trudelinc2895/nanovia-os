from __future__ import annotations

from starlette.requests import Request

from api.core import deps


def _make_request(*, client_host: str, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in (headers or {}).items()
        ],
        "client": (client_host, 12345),
        "server": ("127.0.0.1", 8010),
        "scheme": "http",
    }
    return Request(scope)


def test_request_client_ip_ignores_forwarded_headers_from_untrusted_source(monkeypatch):
    monkeypatch.setattr(deps.settings, "TRUSTED_PROXY_CIDRS_RAW", "127.0.0.1/32")

    request = _make_request(
        client_host="198.51.100.20",
        headers={"X-Forwarded-For": "203.0.113.10", "X-Real-IP": "203.0.113.11"},
    )

    assert deps._request_client_ip(request) == "198.51.100.20"


def test_request_client_ip_uses_cf_connecting_ip_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(deps.settings, "TRUSTED_PROXY_CIDRS_RAW", "10.0.0.0/8")

    request = _make_request(
        client_host="10.0.0.15",
        headers={"CF-Connecting-IP": "203.0.113.10", "X-Forwarded-For": "198.51.100.12"},
    )

    assert deps._request_client_ip(request) == "203.0.113.10"


def test_request_client_ip_supports_testclient_forwarded_headers(monkeypatch):
    monkeypatch.setattr(deps.settings, "TRUSTED_PROXY_CIDRS_RAW", "127.0.0.1/32")

    request = _make_request(
        client_host="testclient",
        headers={"X-Forwarded-For": "203.0.113.10"},
    )

    assert deps._request_client_ip(request) == "203.0.113.10"
