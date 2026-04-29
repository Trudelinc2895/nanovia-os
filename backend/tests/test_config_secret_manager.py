"""Regression tests for managed secret resolution."""

from __future__ import annotations

from unittest.mock import patch

from api.config import Settings


def test_settings_prefers_explicit_env_value_over_vault_ref(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_secret_manager_env.db")
    monkeypatch.setenv("SECRET_PROVIDER", "auto")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY_REF", "vault://secret/nanovia/backend#jwt_secret_key")

    with patch("api.core.secret_manager.fetch_vault_secret") as fetch_mock:
        settings = Settings(_env_file=None)

    assert settings.JWT_SECRET_KEY == "x" * 40
    fetch_mock.assert_not_called()


def test_settings_resolves_vault_secret_reference(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_secret_manager_vault.db")
    monkeypatch.setenv("SECRET_PROVIDER", "auto")
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8200")
    monkeypatch.setenv("VAULT_TOKEN", "vault-token")
    monkeypatch.setenv("JWT_SECRET_KEY_REF", "vault://secret/nanovia/backend#jwt_secret_key")

    with patch(
        "api.core.secret_manager.fetch_vault_secret",
        return_value="vault-secret-key-minimum-32-chars-long",
    ) as fetch_mock:
        settings = Settings(_env_file=None)

    assert settings.JWT_SECRET_KEY == "vault-secret-key-minimum-32-chars-long"
    fetch_mock.assert_called_once()
