from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validate_runtime_env.py"
_SPEC = importlib.util.spec_from_file_location("validate_runtime_env_script", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
load_env_file = _MODULE.load_env_file
resolve_target_env = _MODULE.resolve_target_env
validate_runtime_env = _MODULE.validate_runtime_env


def test_production_runtime_env_requires_admin_allowlist_and_totp_key():
    errors = validate_runtime_env(
        {
            "APP_ENV": "production",
            "JWT_SECRET_KEY": "x" * 32,
            "STRIPE_SECRET_KEY": "sk" + "_live_prod",
            "STRIPE_PUBLIC_KEY": "stripe_public_prod",
            "STRIPE_WEBHOOK_SECRET": "stripe_webhook_prod",
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://www.nanovia.ca",
            "NEXT_PUBLIC_API_URL": "",
        },
        target_env="production",
    )

    assert "Production requires ADMIN_ALLOWED_IPS/ADMIN_ALLOWED_IP to be configured" in errors
    assert "TOTP_ENCRYPTION_KEY must be set to a non-placeholder Fernet key" in errors


def test_production_runtime_env_accepts_safe_values():
    errors = validate_runtime_env(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:pass@postgres:5432/nanovia",
            "REDIS_URL": "redis://redis:6379/0",
            "GRAFANA_ADMIN_USER": "admin",
            "JWT_SECRET_KEY": "x" * 40,
            "TOTP_ENCRYPTION_KEY": "safe-fernet-key-placeholder-free",
            "STRIPE_SECRET_KEY": "sk" + "_live_prod",
            "STRIPE_PUBLIC_KEY": "pk" + "_live_prod",
            "STRIPE_WEBHOOK_SECRET": "wh" + "sec_prod",
            "ADMIN_ALLOWED_IP": "203.0.113.10/32",
            "AI_ADMIN_API_KEY": "nanovia-ai-admin-key-safe-01",
            "AI_STATE_DIR": "/var/lib/nanovia-ai",
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://www.nanovia.ca",
            "API_BASE_URL": "https://nanovia.ca",
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
            "NEXT_PUBLIC_API_URL": "https://nanovia.ca",
        },
        target_env="production",
    )

    assert errors == []


def test_production_runtime_env_accepts_turnstile_when_enabled():
    errors = validate_runtime_env(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:pass@postgres:5432/nanovia",
            "REDIS_URL": "redis://redis:6379/0",
            "JWT_SECRET_KEY": "x" * 40,
            "TOTP_ENCRYPTION_KEY": "safe-fernet-key-placeholder-free",
            "STRIPE_SECRET_KEY": "sk" + "_live_prod",
            "STRIPE_PUBLIC_KEY": "pk" + "_live_prod",
            "STRIPE_WEBHOOK_SECRET": "wh" + "sec_prod",
            "TURNSTILE_ENABLED": "true",
            "TURNSTILE_SITE_KEY": "site-key",
            "TURNSTILE_SECRET_KEY": "secret-key",
            "ADMIN_ALLOWED_IP": "203.0.113.10/32",
            "AI_ADMIN_API_KEY": "nanovia-ai-admin-key-safe-01",
            "AI_STATE_DIR": "/var/lib/nanovia-ai",
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://www.nanovia.ca",
            "API_BASE_URL": "https://nanovia.ca",
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
            "NEXT_PUBLIC_API_URL": "https://nanovia.ca",
        },
        target_env="production",
    )

    assert errors == []


def test_runtime_env_detects_conflicting_alias_values():
    errors = validate_runtime_env(
        {
            "APP_ENV": "development",
            "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
            "REDIS_URL": "redis://localhost:6379/0",
            "JWT_SECRET_KEY": "x" * 40,
            "JWT_SECRET": "y" * 40,
        },
        target_env="development",
    )

    assert any("Conflicting alias values for JWT_SECRET_KEY/JWT_SECRET/SECRET_KEY" in error for error in errors)


def test_runtime_env_detects_unknown_keys():
    errors = validate_runtime_env(
        {
            "APP_ENV": "development",
            "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
            "REDIS_URL": "redis://localhost:6379/0",
            "JWT_SECRET_KEY": "x" * 40,
            "MYSTERY_FLAG": "enabled",
        },
        target_env="development",
    )

    assert "Unknown env key: MYSTERY_FLAG" in errors


def test_staging_runtime_env_rejects_public_bind_and_live_stripe():
    errors = validate_runtime_env(
        {
            "APP_ENV": "staging",
            "JWT_SECRET_KEY": "x" * 40,
            "TOTP_ENCRYPTION_KEY": "safe-fernet-key-placeholder-free",
            "STRIPE_SECRET_KEY": "sk" + "_live_prod",
            "STAGING_BIND_ADDRESS": "0.0.0.0",
        },
        target_env="staging",
    )

    assert "Staging refuses live Stripe keys" in errors
    assert "Staging requires STAGING_BIND_ADDRESS to stay loopback-only" in errors


def test_development_runtime_env_accepts_local_settings():
    errors = validate_runtime_env(
        {
            "APP_ENV": "development",
            "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
            "REDIS_URL": "redis://localhost:6379/0",
            "JWT_SECRET_KEY": "x" * 40,
            "STRIPE_SECRET_KEY": "stripe_secret_dev",
            "STRIPE_PUBLIC_KEY": "stripe_public_dev",
        },
        target_env="development",
    )

    assert errors == []


def test_production_template_mode_allows_placeholders():
    errors = validate_runtime_env(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:CHANGE_ME@postgres:5432/nanovia",
            "REDIS_URL": "redis://redis:6379/0",
            "GRAFANA_ADMIN_USER": "admin",
            "JWT_SECRET_KEY": "CHANGE_ME_generate_with_openssl_rand_hex_32",
            "TOTP_ENCRYPTION_KEY": "GENERATE_WITH_FERNET_AND_SET_HERE",
            "STRIPE_SECRET_KEY": "REPLACE_WITH_STRIPE_SECRET_KEY",
            "STRIPE_PUBLIC_KEY": "REPLACE_WITH_STRIPE_PUBLISHABLE_KEY",
            "STRIPE_WEBHOOK_SECRET": "REPLACE_WITH_STRIPE_WEBHOOK_SECRET",
            "ADMIN_ALLOWED_IP": "REPLACE_ME_ADMIN_CIDR",
            "AI_ADMIN_API_KEY": "REPLACE_WITH_AI_ADMIN_API_KEY",
            "AI_STATE_DIR": "/var/lib/nanovia-ai",
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://www.nanovia.ca",
            "API_BASE_URL": "https://nanovia.ca",
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
            "NEXT_PUBLIC_API_URL": "https://nanovia.ca",
        },
        target_env="production",
        allow_placeholders=True,
    )

    assert errors == []


def test_runtime_env_accepts_vault_managed_secret_references():
    errors = validate_runtime_env(
        {
            "APP_ENV": "production",
            "SECRET_PROVIDER": "auto",
            "DATABASE_URL": "postgresql+psycopg://user:pass@postgres:5432/nanovia",
            "REDIS_URL": "redis://redis:6379/0",
            "JWT_SECRET_KEY_REF": "vault://secret/nanovia/backend#jwt_secret_key",
            "TOTP_ENCRYPTION_KEY_REF": "vault://secret/nanovia/backend#totp_encryption_key",
            "STRIPE_SECRET_KEY_REF": "vault://secret/nanovia/backend#stripe_secret_key",
            "STRIPE_WEBHOOK_SECRET_REF": "vault://secret/nanovia/backend#stripe_webhook_secret",
            "STRIPE_PUBLIC_KEY": "pk" + "_live_prod",
            "ADMIN_ALLOWED_IP": "203.0.113.10/32",
            "AI_ADMIN_API_KEY": "nanovia-ai-admin-key-safe-01",
            "AI_STATE_DIR": "/var/lib/nanovia-ai",
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://www.nanovia.ca",
            "API_BASE_URL": "https://nanovia.ca",
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
            "NEXT_PUBLIC_API_URL": "https://nanovia.ca",
            "VAULT_ADDR": "http://127.0.0.1:8200",
            "VAULT_TOKEN": "vault-token",
        },
        target_env="production",
    )

    assert errors == []


def test_runtime_env_requires_vault_token_when_secret_refs_are_enabled():
    errors = validate_runtime_env(
        {
            "APP_ENV": "production",
            "SECRET_PROVIDER": "auto",
            "DATABASE_URL": "postgresql+psycopg://user:pass@postgres:5432/nanovia",
            "REDIS_URL": "redis://redis:6379/0",
            "JWT_SECRET_KEY_REF": "vault://secret/nanovia/backend#jwt_secret_key",
            "STRIPE_SECRET_KEY_REF": "vault://secret/nanovia/backend#stripe_secret_key",
            "STRIPE_WEBHOOK_SECRET_REF": "vault://secret/nanovia/backend#stripe_webhook_secret",
            "STRIPE_PUBLIC_KEY": "pk" + "_live_prod",
            "TOTP_ENCRYPTION_KEY_REF": "vault://secret/nanovia/backend#totp_encryption_key",
            "ADMIN_ALLOWED_IP": "203.0.113.10/32",
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://www.nanovia.ca",
            "API_BASE_URL": "https://nanovia.ca",
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
            "NEXT_PUBLIC_API_URL": "https://nanovia.ca",
            "VAULT_ADDR": "http://127.0.0.1:8200",
        },
        target_env="production",
    )

    assert "VAULT_TOKEN is required when Vault-managed secrets are enabled" in errors


def test_production_runtime_env_rejects_mismatched_frontend_api_url():
    errors = validate_runtime_env(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:pass@postgres:5432/nanovia",
            "REDIS_URL": "redis://redis:6379/0",
            "JWT_SECRET_KEY": "x" * 40,
            "TOTP_ENCRYPTION_KEY": "safe-fernet-key-placeholder-free",
            "STRIPE_SECRET_KEY": "sk" + "_live_prod",
            "STRIPE_PUBLIC_KEY": "pk" + "_live_prod",
            "STRIPE_WEBHOOK_SECRET": "wh" + "sec_prod",
            "ADMIN_ALLOWED_IP": "203.0.113.10/32",
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://www.nanovia.ca",
            "API_BASE_URL": "https://nanovia.ca",
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://nanovia.ca",
            "NEXT_PUBLIC_API_URL": "https://preview-api.nanovia.ca",
        },
        target_env="production",
    )

    assert "Production NEXT_PUBLIC_API_URL must match API_BASE_URL when set" in errors


def test_resolve_target_env_for_examples():
    assert resolve_target_env("infra/env/.env.example", {"APP_ENV": "development"}) == "production"
    assert resolve_target_env("infra/env/.env.staging.example", {"APP_ENV": "development"}) == "staging"
    assert resolve_target_env(".env.example", {"APP_ENV": "development"}) == "development"


def test_sandbox_env_example_accepts_known_keys_and_sandbox_rules():
    env_path = Path(__file__).resolve().parents[2] / ".env.sandbox.example"
    values = load_env_file(env_path)

    errors = validate_runtime_env(values, target_env="sandbox", allow_placeholders=True)

    assert errors == []
