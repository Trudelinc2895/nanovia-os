"""Regression tests for runtime environment variable aliases."""

from __future__ import annotations

from api.config import Settings


def test_settings_accept_legacy_runtime_env_aliases(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_aliases.db")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-minimum-32-chars-long-alias")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "stripe_public_test_alias")

    settings = Settings()

    assert settings.JWT_SECRET_KEY == "test-secret-key-minimum-32-chars-long-alias"
    assert settings.STRIPE_PUBLIC_KEY == "stripe_public_test_alias"
