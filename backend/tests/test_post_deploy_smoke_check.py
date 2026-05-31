from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "post_deploy_smoke_check.py"
_SPEC = importlib.util.spec_from_file_location("post_deploy_smoke_check_script", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
run_smoke_checks = _MODULE.run_smoke_checks


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_run_smoke_checks_accepts_hardened_public_surface(monkeypatch):
    responses = {
        "https://nanovia.ca": _Response(200),
        "https://nanovia.ca/health": _Response(200),
        "https://nanovia.ca/ready": _Response(200),
        "https://nanovia.ca/metrics": _Response(403),
        "https://nanovia.ca/api/v1/billing/plans": _Response(200),
        "https://admin.nanovia.ca": _Response(302),
    }

    monkeypatch.setattr(_MODULE, "_request", lambda method, url, timeout, allow_redirects=False: responses[url])

    errors, warnings = run_smoke_checks(
        {
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
        },
        timeout=2.0,
    )

    assert errors == []
    assert warnings == []


def test_run_smoke_checks_flags_public_metrics_and_broken_admin(monkeypatch):
    responses = {
        "https://nanovia.ca": _Response(200),
        "https://nanovia.ca/health": _Response(200),
        "https://nanovia.ca/ready": _Response(200),
        "https://nanovia.ca/metrics": _Response(200),
        "https://nanovia.ca/api/v1/billing/plans": _Response(503),
        "https://admin.nanovia.ca": _Response(525),
    }

    monkeypatch.setattr(_MODULE, "_request", lambda method, url, timeout, allow_redirects=False: responses[url])

    errors, warnings = run_smoke_checks(
        {
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
        },
        timeout=2.0,
    )

    assert any("metrics endpoint should not be public" in error for error in errors)
    assert any("private admin host returned 525" in error for error in errors)
    assert any("billing plans returned 503" in warning for warning in warnings)
