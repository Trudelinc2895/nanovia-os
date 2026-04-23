"""Regression tests for runtime environment variable aliases."""

from __future__ import annotations

from cryptography.fernet import Fernet
import pytest

from api.config import Settings


def test_settings_accept_legacy_runtime_env_aliases(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("ADMIN_ALLOWED_IPS_RAW", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_aliases.db")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-minimum-32-chars-long-alias")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_alias")
    monkeypatch.setenv("ADMIN_ALLOWED_IP", "203.0.113.10/32")

    settings = Settings()

    assert settings.JWT_SECRET_KEY == "test-secret-key-minimum-32-chars-long-alias"
    assert settings.STRIPE_PUBLIC_KEY == "pk_test_alias"
    assert settings.ADMIN_ALLOWED_IPS == ["203.0.113.10/32"]


def test_settings_accept_secret_key_legacy_alias(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_secret_key_alias.db")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-minimum-32-chars-long-secret")

    settings = Settings()

    assert settings.JWT_SECRET_KEY == "test-secret-key-minimum-32-chars-long-secret"


def test_production_requires_admin_allowlist_and_totp_encryption(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_prod_security.db")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-minimum-32-chars-long-prod")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_prod")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_prod")
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://nanovia.ca")
    monkeypatch.setenv("PRIVATE_ADMIN_URL", "https://admin.nanovia.ca")
    monkeypatch.setenv(
        "ALLOWED_ORIGINS_RAW",
        "https://nanovia.ca,https://www.nanovia.ca,https://admin.nanovia.ca",
    )
    monkeypatch.delenv("ADMIN_ALLOWED_IPS_RAW", raising=False)
    monkeypatch.delenv("ADMIN_ALLOWED_IPS", raising=False)
    monkeypatch.delenv("ADMIN_ALLOWED_IP", raising=False)
    monkeypatch.delenv("TOTP_ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValueError) as exc_info:
        Settings()

    message = str(exc_info.value)
    assert "ADMIN_ALLOWED_IPS/ADMIN_ALLOWED_IP is required in production" in message
    assert "TOTP_ENCRYPTION_KEY is required in production" in message


def test_production_accepts_valid_totp_encryption_and_admin_allowlist(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_prod_security_ok.db")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-minimum-32-chars-long-prod")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_prod")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_prod")
    monkeypatch.setenv("API_BASE_URL", "https://nanovia.ca")
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://nanovia.ca")
    monkeypatch.setenv("PRIVATE_ADMIN_URL", "https://admin.nanovia.ca")
    monkeypatch.setenv(
        "ALLOWED_ORIGINS_RAW",
        "https://nanovia.ca,https://www.nanovia.ca,https://admin.nanovia.ca",
    )
    monkeypatch.setenv("ADMIN_ALLOWED_IP", "203.0.113.10/32")
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())

    settings = Settings()

    assert settings.ADMIN_ALLOWED_IPS == ["203.0.113.10/32"]


def test_production_requires_https_public_urls(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_prod_https.db")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-minimum-32-chars-long-prod")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_prod")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_prod")
    monkeypatch.setenv("ADMIN_ALLOWED_IP", "203.0.113.10/32")
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("API_BASE_URL", "http://nanovia.ca")
    monkeypatch.setenv("PUBLIC_WEB_URL", "http://nanovia.ca")
    monkeypatch.setenv("PRIVATE_ADMIN_URL", "http://admin.nanovia.ca")
    monkeypatch.setenv(
        "ALLOWED_ORIGINS_RAW",
        "https://nanovia.ca,https://www.nanovia.ca,https://admin.nanovia.ca",
    )

    with pytest.raises(ValueError) as exc_info:
        Settings()

    message = str(exc_info.value)
    assert "API_BASE_URL must use https:// in production" in message
    assert "PUBLIC_WEB_URL must use https:// in production" in message
    assert "PRIVATE_ADMIN_URL must use https:// in production" in message
