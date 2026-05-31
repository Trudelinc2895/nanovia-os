from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "preflight_prod_check.py"
_SPEC = importlib.util.spec_from_file_location("preflight_prod_check_script", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
collect_go_live_warnings = _MODULE.collect_go_live_warnings
validate_public_endpoints = _MODULE.validate_public_endpoints
validate_static_prod_layout = _MODULE.validate_static_prod_layout


def test_validate_static_prod_layout_accepts_hardened_files(tmp_path: Path):
    compose_path = tmp_path / "docker-compose.prod.yml"
    caddy_path = tmp_path / "Caddyfile"
    backup_path = tmp_path / "backup.sh"

    compose_path.write_text(
        """services:
  caddy:
    ports:
      - "80:80"
      - "443:443"
  api:
    volumes:
      - ai_state:/var/lib/nanovia-ai
  postgres:
    volumes:
      - postgres_data:/var/lib/postgresql/data
  redis:
    volumes:
      - redis_data:/data
""",
        encoding="utf-8",
    )
    caddy_path.write_text(
        """(admin_ip_allow) {
    @not_allowed not remote_ip {$ADMIN_ALLOWED_IP}
    respond @not_allowed 403
}

{$DOMAIN:nanovia.ca}, {$WWW_DOMAIN:www.nanovia.ca} {
    handle /metrics {
        import admin_ip_allow
    }
}

{$PRIVATE_ADMIN_HOST:admin.nanovia.ca} {
    import admin_ip_allow
}
""",
        encoding="utf-8",
    )
    backup_path.write_text(
        """PASSPHRASE_FILE=/etc/nanovia-backup.key
openssl rand -base64 48 > "$PASSPHRASE_FILE"
openssl enc -aes-256-cbc -pbkdf2 -iter 100000
sha256sum "$BACKUP_FILE"
""",
        encoding="utf-8",
    )

    errors = validate_static_prod_layout(
        compose_path=compose_path,
        caddy_path=caddy_path,
        backup_path=backup_path,
    )

    assert errors == []


def test_validate_static_prod_layout_detects_missing_admin_and_persistence(tmp_path: Path):
    compose_path = tmp_path / "docker-compose.prod.yml"
    caddy_path = tmp_path / "Caddyfile"
    backup_path = tmp_path / "backup.sh"

    compose_path.write_text("services:\n  caddy:\n    ports:\n      - \"80:80\"\n", encoding="utf-8")
    caddy_path.write_text("{$DOMAIN:nanovia.ca}, {$WWW_DOMAIN:www.nanovia.ca} {\n}\n", encoding="utf-8")
    backup_path.write_text("# no encryption here\n", encoding="utf-8")

    errors = validate_static_prod_layout(
        compose_path=compose_path,
        caddy_path=caddy_path,
        backup_path=backup_path,
    )

    assert any("persistent AI state" in error for error in errors)
    assert any("protect /metrics" in error for error in errors)
    assert any("private admin surface" in error for error in errors)
    assert any("encrypt backups" in error for error in errors)


def test_collect_go_live_warnings_flags_optional_runtime_gaps():
    warnings = collect_go_live_warnings(
        {
            "TURNSTILE_ENABLED": "false",
            "STRIPE_SECRET_KEY": "sk_live_value",
            "STRIPE_PUBLIC_KEY": "pk_live_value",
            "STRIPE_WEBHOOK_SECRET": "whsec_value",
        }
    )

    assert "RESEND_API_KEY is absent; transactional emails stay log-only" in warnings
    assert "Telegram alert routing is incomplete; Alertmanager notifications may be silent" in warnings
    assert "OPENAI_API_KEY is absent; AI features will be unavailable or degraded" in warnings
    assert "No STRIPE_PRICE_* live identifiers are configured; Stripe checkout may be incomplete" in warnings
    assert "TURNSTILE_ENABLED is not true; billing and auth bot protection is reduced" in warnings


def test_validate_public_endpoints_uses_env_hosts(monkeypatch):
    seen: list[str] = []

    def fake_check_host(host: str, timeout: float):
        seen.append(host)
        return host == "nanovia.ca", ["203.0.113.10"], "ok" if host == "nanovia.ca" else "tls failed"

    monkeypatch.setattr(_MODULE, "check_host", fake_check_host)

    errors = validate_public_endpoints(
        {
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
        },
        timeout=2.0,
    )

    assert seen == ["nanovia.ca", "admin.nanovia.ca"]
    assert errors == ["admin.nanovia.ca DNS/TLS check failed: tls failed"]
