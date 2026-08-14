from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from api.services.pilot_stripe_contract_service import (
    PilotStripeContractError,
    load_pilot_stripe_config,
)


_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validate_runtime_env.py"
_SPEC = importlib.util.spec_from_file_location("validate_runtime_env_script", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
resolve_target_env = _MODULE.resolve_target_env
validate_runtime_env = _MODULE.validate_runtime_env


def _complete_production_values() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://test:test@postgres:5432/test",
        "REDIS_URL": "redis://redis:6379/0",
        "JWT_SECRET_KEY": "x" * 40,
        "TOTP_ENCRYPTION_KEY": "safe-test-value-without-production-secret",
        "STRIPE_SECRET_KEY": "sk" + "_live_test_value",
        "STRIPE_PUBLIC_KEY": "pk" + "_live_test_value",
        "STRIPE_WEBHOOK_SECRET": "wh" + "sec_test_value",
        "ADMIN_ALLOWED_IP": "203.0.113.10/32",
        "DOMAIN": "nanovia.ca",
        "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://admin.nanovia.ca",
        "API_BASE_URL": "https://nanovia.ca",
        "PUBLIC_WEB_URL": "https://nanovia.ca",
        "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
        "NEXT_PUBLIC_API_URL": "",
        "CONTACT_RECIPIENT_EMAIL": "pilot@example.invalid",
        "STRIPE_ACCOUNT_ID": "acct_test123",
        "STRIPE_PILOT_PRODUCT_ID": "prod_test123",
        "STRIPE_PILOT_PRICE_ID": "price_test123",
        "STRIPE_PILOT_PAYMENT_LINK_ID": "plink_test123",
        "STRIPE_PILOT_PAYMENT_LINK_URL": "https://buy.stripe.com/ABC123",
    }


def test_production_runtime_env_requires_admin_allowlist_and_totp_key():
    errors = validate_runtime_env(
        {
            "APP_ENV": "production",
            "JWT_SECRET_KEY": "x" * 32,
            "STRIPE_SECRET_KEY": "sk" + "_live_prod",
            "STRIPE_PUBLIC_KEY": "stripe_public_prod",
            "STRIPE_WEBHOOK_SECRET": "stripe_webhook_prod",
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://admin.nanovia.ca",
            "NEXT_PUBLIC_API_URL": "",
        },
        target_env="production",
    )

    assert "Production requires ADMIN_ALLOWED_IPS/ADMIN_ALLOWED_IP to be configured" in errors
    assert "TOTP_ENCRYPTION_KEY must be set to a non-placeholder Fernet key" in errors


def test_production_runtime_env_accepts_safe_values():
    errors = validate_runtime_env(_complete_production_values(), target_env="production")

    assert errors == []


@pytest.mark.parametrize(
    "key",
    ("API_BASE_URL", "PUBLIC_WEB_URL", "PRIVATE_ADMIN_URL"),
)
def test_production_external_urls_require_https(key: str):
    values = _complete_production_values()
    values[key] = "http://external.nanovia.invalid"

    errors = validate_runtime_env(values, target_env="production")

    assert f"Production {key} must use https://" in errors


@pytest.mark.parametrize(
    "key",
    ("API_BASE_URL", "PUBLIC_WEB_URL", "PRIVATE_ADMIN_URL"),
)
def test_production_external_url_canonicalization_policy(key: str):
    values = _complete_production_values()
    values[key] = "https://external.nanovia.invalid:443/path?mode=kept#fragment"

    errors = validate_runtime_env(values, target_env="production")

    assert f"Production {key} must use https://" not in errors
    if key == "PUBLIC_WEB_URL":
        assert (
            "Production PUBLIC_WEB_URL must be the canonical HTTPS URL for DOMAIN"
            in errors
        )


@pytest.mark.parametrize(
    "value",
    (
        " http://external.nanovia.invalid",
        "http://external.nanovia.invalid ",
        " https://external.nanovia.invalid",
        "https://external.nanovia.invalid ",
    ),
)
def test_production_external_urls_reject_surrounding_whitespace(value: str):
    values = _complete_production_values()
    values["PUBLIC_WEB_URL"] = value

    errors = validate_runtime_env(values, target_env="production")

    assert "Production PUBLIC_WEB_URL must use https://" in errors


def test_development_keeps_http_external_urls_supported():
    values = {
        "APP_ENV": "development",
        "API_BASE_URL": "http://127.0.0.1:8010",
        "PUBLIC_WEB_URL": "http://127.0.0.1:3000",
        "PRIVATE_ADMIN_URL": "http://127.0.0.1:3020",
    }

    errors = validate_runtime_env(values, target_env="development")

    assert not any("must use https://" in error for error in errors)


def test_nonproduction_runtime_env_does_not_require_domain():
    values = {
        "APP_ENV": "development",
        "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET_KEY": "x" * 40,
    }

    errors = validate_runtime_env(values, target_env="development")

    assert not any("DOMAIN" in error for error in errors)


def test_production_domain_is_required():
    values = _complete_production_values()
    values.pop("DOMAIN")

    errors = validate_runtime_env(values, target_env="production")

    assert "Production DOMAIN is required" in errors


@pytest.mark.parametrize(
    "domain",
    (
        "",
        "localhost",
        "127.0.0.1",
        "2001:db8::1",
        "CHANGE_ME_DOMAIN",
        "example.com",
        "nanovia.invalid",
        "https://nanovia.ca",
        "nanovia.ca:443",
        "nanovia.ca/path",
        "nanovia.ca?query=yes",
        "nanovia.ca#fragment",
        "*.nanovia.ca",
        "bad..nanovia.ca",
        "-bad.nanovia.ca",
        "Nanovia.ca",
        "nanovia.ca.",
        " nanovia.ca",
        "nanovia.ca ",
    ),
)
def test_production_domain_rejects_noncanonical_values(domain: str):
    values = _complete_production_values()
    values["DOMAIN"] = domain

    errors = validate_runtime_env(values, target_env="production")

    expected = (
        "Production DOMAIN is required"
        if not domain
        else "Production DOMAIN must be a canonical DNS hostname"
    )
    assert expected in errors


@pytest.mark.parametrize(
    "public_web_url",
    (
        "",
        "http://nanovia.ca",
        "https://user@nanovia.ca",
        "https://nanovia.ca:444",
        "https://nanovia.ca/",
        "https://nanovia.ca/path",
        "https://nanovia.ca?query=yes",
        "https://nanovia.ca#fragment",
        "https://www.nanovia.ca",
        "https://NANOVIA.ca",
        " https://nanovia.ca",
        "https://nanovia.ca ",
    ),
)
def test_production_public_web_url_rejects_noncanonical_values(
    public_web_url: str,
):
    values = _complete_production_values()
    values["PUBLIC_WEB_URL"] = public_web_url

    errors = validate_runtime_env(values, target_env="production")

    expected = (
        "Production PUBLIC_WEB_URL is required"
        if not public_web_url
        else "Production PUBLIC_WEB_URL must be the canonical HTTPS URL for DOMAIN"
    )
    assert expected in errors


@pytest.mark.parametrize(
    "public_web_url",
    ("https://nanovia.ca", "https://nanovia.ca:443"),
)
def test_production_accepts_canonical_domain_and_public_url_pair(
    public_web_url: str,
):
    values = _complete_production_values()
    values["PUBLIC_WEB_URL"] = public_web_url

    errors = validate_runtime_env(values, target_env="production")

    assert errors == []


def test_runtime_env_cli_rejects_invalid_domain_without_exposing_values(tmp_path):
    values = _complete_production_values()
    values["DOMAIN"] = " nanovia.ca"
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--env-file",
            str(env_file),
            "--target-env",
            "production",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Production DOMAIN must be a canonical DNS hostname" in completed.stderr
    assert "nanovia.ca" not in completed.stderr


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("PRIVATE_ORCHESTRATOR_UPSTREAM_URL", "http://ai-orchestrator:8020"),
        ("OLLAMA_CLIENT_BASE_URL", "http://ollama:11434"),
        ("OLLAMA_ADMIN_BASE_URL", "http://ollama:11435"),
        ("VAULT_ADDR", "http://vault:8200"),
    ),
)
def test_production_keeps_internal_http_service_urls_supported(key: str, value: str):
    values = _complete_production_values()
    values[key] = value

    errors = validate_runtime_env(values, target_env="production")

    assert not any(key in error and "must use https://" in error for error in errors)


def _runtime_accepts_payment_link_url(value: str, *, app_env: str) -> bool:
    settings = SimpleNamespace(
        APP_ENV=app_env,
        STRIPE_ACCOUNT_ID="acct_ABC123",
        STRIPE_PILOT_PRODUCT_ID="prod_ABC123",
        STRIPE_PILOT_PRICE_ID="price_ABC123",
        STRIPE_PILOT_PAYMENT_LINK_ID="plink_ABC123",
        STRIPE_PILOT_PAYMENT_LINK_URL=value,
    )
    try:
        load_pilot_stripe_config(settings)
    except PilotStripeContractError:
        return False
    return True


@pytest.mark.parametrize(
    "value",
    (
        "https://buy.stripe.com/ABC123",
        "https://buy.stripe.com:443/ABC123",
    ),
)
def test_pilot_payment_link_url_matches_runtime_for_canonical_values(value: str):
    values = _complete_production_values()
    values["STRIPE_PILOT_PAYMENT_LINK_URL"] = value

    errors = validate_runtime_env(values, target_env="production")

    assert errors == []
    assert _runtime_accepts_payment_link_url(value, app_env="production") is True


@pytest.mark.parametrize(
    "value",
    (
        "http://buy.stripe.com/ABC123",
        "https://example.com/ABC123",
        "https://user@buy.stripe.com/ABC123",
        "https://buy.stripe.com:444/ABC123",
        "https://buy.stripe.com/ABC123?locale=fr",
        "https://buy.stripe.com/ABC123#fragment",
        "https://buy.stripe.com/",
        "https://buy.stripe.com/test_ABC123",
    ),
)
def test_pilot_payment_link_url_rejects_runtime_contract_mismatches(value: str):
    values = _complete_production_values()
    values["STRIPE_PILOT_PAYMENT_LINK_URL"] = value

    errors = validate_runtime_env(values, target_env="production")

    assert (
        "STRIPE_PILOT_PAYMENT_LINK_URL must use a canonical "
        "https://buy.stripe.com/... URL"
    ) in errors
    assert _runtime_accepts_payment_link_url(value, app_env="production") is False


@pytest.mark.parametrize(
    "value",
    (
        " https://buy.stripe.com/ABC123",
        "https://buy.stripe.com/ABC123 ",
        "https://buy.stripe.com/ABC 123",
        "https://buy.stripe.com/ABC%20123",
        "https://buy.stripe.com/ABC-123",
        "https://buy.stripe.com/ABC123/extra",
        "https://BUY.stripe.com/ABC123",
    ),
)
def test_pilot_payment_link_url_rejects_ambiguous_or_normalized_paths(value: str):
    values = _complete_production_values()
    values["STRIPE_PILOT_PAYMENT_LINK_URL"] = value

    errors = validate_runtime_env(values, target_env="production")

    assert (
        "STRIPE_PILOT_PAYMENT_LINK_URL must use a canonical "
        "https://buy.stripe.com/... URL"
    ) in errors


@pytest.mark.parametrize(
    ("key", "value", "error"),
    (
        (
            "STRIPE_ACCOUNT_ID",
            "acct_ABC123",
            "STRIPE_ACCOUNT_ID must use the acct_... format",
        ),
        (
            "STRIPE_PILOT_PRODUCT_ID",
            "prod_ABC123",
            "STRIPE_PILOT_PRODUCT_ID must use the prod_... format",
        ),
        (
            "STRIPE_PILOT_PRICE_ID",
            "price_ABC123",
            "STRIPE_PILOT_PRICE_ID must use the price_... format",
        ),
        (
            "STRIPE_PILOT_PAYMENT_LINK_ID",
            "plink_ABC123",
            "STRIPE_PILOT_PAYMENT_LINK_ID must use the plink_... format",
        ),
    ),
)
def test_pilot_stripe_ids_accept_canonical_alphanumeric_suffix(
    key: str,
    value: str,
    error: str,
):
    values = _complete_production_values()
    values[key] = value

    errors = validate_runtime_env(values, target_env="production")

    assert error not in errors


@pytest.mark.parametrize(
    ("key", "value", "error"),
    (
        (
            "STRIPE_ACCOUNT_ID",
            "acct_bad_id",
            "STRIPE_ACCOUNT_ID must use the acct_... format",
        ),
        (
            "STRIPE_PILOT_PRODUCT_ID",
            "prod_bad_id",
            "STRIPE_PILOT_PRODUCT_ID must use the prod_... format",
        ),
        (
            "STRIPE_PILOT_PRICE_ID",
            "price_bad_id",
            "STRIPE_PILOT_PRICE_ID must use the price_... format",
        ),
        (
            "STRIPE_PILOT_PAYMENT_LINK_ID",
            "plink_bad_id",
            "STRIPE_PILOT_PAYMENT_LINK_ID must use the plink_... format",
        ),
    ),
)
def test_pilot_stripe_ids_reject_second_underscore(
    key: str,
    value: str,
    error: str,
):
    values = _complete_production_values()
    values[key] = value

    errors = validate_runtime_env(values, target_env="production")

    assert error in errors
    assert value not in "\n".join(errors)


@pytest.mark.parametrize(
    "invalid_value",
    (
        "plink_bad_id",
        "plink_test_123",
        "plink_",
        "plink_test 123",
        "plink_test-123",
        "payment_link_test123",
    ),
)
def test_pilot_payment_link_id_rejects_noncanonical_formats(invalid_value: str):
    values = _complete_production_values()
    values["STRIPE_PILOT_PAYMENT_LINK_ID"] = invalid_value

    errors = validate_runtime_env(values, target_env="production")

    expected_error = "STRIPE_PILOT_PAYMENT_LINK_ID must use the plink_... format"
    assert errors.count(expected_error) == 1


@pytest.mark.parametrize(
    "key",
    (
        "CONTACT_RECIPIENT_EMAIL",
        "STRIPE_ACCOUNT_ID",
        "STRIPE_PILOT_PRODUCT_ID",
        "STRIPE_PILOT_PRICE_ID",
        "STRIPE_PILOT_PAYMENT_LINK_ID",
        "STRIPE_PILOT_PAYMENT_LINK_URL",
    ),
)
@pytest.mark.parametrize("missing_value", (None, "", "   "))
def test_production_runtime_env_requires_each_pilot_key(key: str, missing_value: str | None):
    values = _complete_production_values()
    if missing_value is None:
        values.pop(key)
    else:
        values[key] = missing_value

    errors = validate_runtime_env(values, target_env="production")

    assert f"{key} is required in production" in errors


@pytest.mark.parametrize(
    ("key", "invalid_value", "expected_error"),
    (
        (
            "CONTACT_RECIPIENT_EMAIL",
            "not-an-email",
            "CONTACT_RECIPIENT_EMAIL must be a valid email address",
        ),
        (
            "STRIPE_ACCOUNT_ID",
            "account_test123",
            "STRIPE_ACCOUNT_ID must use the acct_... format",
        ),
        (
            "STRIPE_PILOT_PRODUCT_ID",
            "product_test123",
            "STRIPE_PILOT_PRODUCT_ID must use the prod_... format",
        ),
        (
            "STRIPE_PILOT_PRICE_ID",
            "pilot_price_test123",
            "STRIPE_PILOT_PRICE_ID must use the price_... format",
        ),
        (
            "STRIPE_PILOT_PAYMENT_LINK_ID",
            "payment_link_test123",
            "STRIPE_PILOT_PAYMENT_LINK_ID must use the plink_... format",
        ),
        (
            "STRIPE_PILOT_PAYMENT_LINK_URL",
            "https://example.invalid/not-stripe",
            "STRIPE_PILOT_PAYMENT_LINK_URL must use a canonical https://buy.stripe.com/... URL",
        ),
    ),
)
def test_production_runtime_env_rejects_each_invalid_pilot_format(
    key: str,
    invalid_value: str,
    expected_error: str,
):
    values = _complete_production_values()
    values[key] = invalid_value

    errors = validate_runtime_env(values, target_env="production")

    assert expected_error in errors
    assert invalid_value not in "\n".join(errors)


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


def test_runtime_env_accepts_valid_pilot_environment_keys():
    errors = validate_runtime_env(
        {
            "APP_ENV": "development",
            "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
            "REDIS_URL": "redis://localhost:6379/0",
            "JWT_SECRET_KEY": "x" * 40,
            "CONTACT_RECIPIENT_EMAIL": "pilot@example.invalid",
            "STRIPE_ACCOUNT_ID": "acct_test123",
            "STRIPE_PILOT_PAYMENT_LINK_ID": "plink_test123",
            "STRIPE_PILOT_PAYMENT_LINK_URL": "https://buy.stripe.com/test_123",
            "STRIPE_PILOT_PRICE_ID": "price_test123",
            "STRIPE_PILOT_PRODUCT_ID": "prod_test123",
        },
        target_env="development",
    )

    assert errors == []


def test_runtime_env_rejects_invalid_pilot_environment_key_formats():
    errors = validate_runtime_env(
        {
            "APP_ENV": "development",
            "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
            "REDIS_URL": "redis://localhost:6379/0",
            "JWT_SECRET_KEY": "x" * 40,
            "CONTACT_RECIPIENT_EMAIL": "not-an-email",
            "STRIPE_ACCOUNT_ID": "account_123",
            "STRIPE_PILOT_PAYMENT_LINK_ID": "payment_link_123",
            "STRIPE_PILOT_PAYMENT_LINK_URL": "http://example.invalid/not-stripe",
            "STRIPE_PILOT_PRICE_ID": "pilot_price_123",
            "STRIPE_PILOT_PRODUCT_ID": "pilot_product_123",
        },
        target_env="development",
    )

    assert set(errors) == {
        "CONTACT_RECIPIENT_EMAIL must be a valid email address",
        "STRIPE_ACCOUNT_ID must use the acct_... format",
        "STRIPE_PILOT_PAYMENT_LINK_ID must use the plink_... format",
        "STRIPE_PILOT_PAYMENT_LINK_URL must use a canonical https://buy.stripe.com/... URL",
        "STRIPE_PILOT_PRICE_ID must use the price_... format",
        "STRIPE_PILOT_PRODUCT_ID must use the prod_... format",
    }


def test_runtime_env_allows_unconfigured_or_placeholder_pilot_keys():
    errors = validate_runtime_env(
        {
            "APP_ENV": "development",
            "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
            "REDIS_URL": "redis://localhost:6379/0",
            "JWT_SECRET_KEY": "x" * 40,
            "CONTACT_RECIPIENT_EMAIL": "",
            "STRIPE_ACCOUNT_ID": "REPLACE_WITH_STRIPE_ACCOUNT_ID",
            "STRIPE_PILOT_PAYMENT_LINK_ID": "REPLACE_WITH_PAYMENT_LINK_ID",
            "STRIPE_PILOT_PAYMENT_LINK_URL": "REPLACE_WITH_PAYMENT_LINK_URL",
            "STRIPE_PILOT_PRICE_ID": "REPLACE_WITH_PRICE_ID",
            "STRIPE_PILOT_PRODUCT_ID": "REPLACE_WITH_PRODUCT_ID",
        },
        target_env="development",
    )

    assert errors == []


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
            "JWT_SECRET_KEY": "CHANGE_ME_generate_with_openssl_rand_hex_32",
            "TOTP_ENCRYPTION_KEY": "GENERATE_WITH_FERNET_AND_SET_HERE",
            "STRIPE_SECRET_KEY": "REPLACE_WITH_STRIPE_SECRET_KEY",
            "STRIPE_PUBLIC_KEY": "REPLACE_WITH_STRIPE_PUBLISHABLE_KEY",
            "STRIPE_WEBHOOK_SECRET": "REPLACE_WITH_STRIPE_WEBHOOK_SECRET",
            "ADMIN_ALLOWED_IP": "REPLACE_ME_ADMIN_CIDR",
            "DOMAIN": "nanovia.ca",
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://admin.nanovia.ca",
            "API_BASE_URL": "https://nanovia.ca",
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
            "NEXT_PUBLIC_API_URL": "",
        },
        target_env="production",
        allow_placeholders=True,
    )

    assert errors == []


def test_runtime_env_accepts_vault_managed_secret_references():
    values = _complete_production_values()
    for key in (
        "JWT_SECRET_KEY",
        "TOTP_ENCRYPTION_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
    ):
        values.pop(key)
    values.update(
        {
            "SECRET_PROVIDER": "auto",
            "JWT_SECRET_KEY_REF": "vault://secret/nanovia/backend#jwt_secret_key",
            "TOTP_ENCRYPTION_KEY_REF": "vault://secret/nanovia/backend#totp_encryption_key",
            "STRIPE_SECRET_KEY_REF": "vault://secret/nanovia/backend#stripe_secret_key",
            "STRIPE_WEBHOOK_SECRET_REF": "vault://secret/nanovia/backend#stripe_webhook_secret",
            "VAULT_ADDR": "http://127.0.0.1:8200",
            "VAULT_TOKEN": "vault-token",
        }
    )

    errors = validate_runtime_env(values, target_env="production")

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
            "ALLOWED_ORIGINS_RAW": "https://nanovia.ca,https://admin.nanovia.ca",
            "API_BASE_URL": "https://nanovia.ca",
            "PUBLIC_WEB_URL": "https://nanovia.ca",
            "PRIVATE_ADMIN_URL": "https://admin.nanovia.ca",
            "NEXT_PUBLIC_API_URL": "",
            "VAULT_ADDR": "http://127.0.0.1:8200",
        },
        target_env="production",
    )

    assert "VAULT_TOKEN is required when Vault-managed secrets are enabled" in errors


def test_resolve_target_env_for_examples():
    assert resolve_target_env("infra/env/.env.example", {"APP_ENV": "development"}) == "production"
    assert resolve_target_env("infra/env/.env.staging.example", {"APP_ENV": "development"}) == "staging"
    assert resolve_target_env(".env.example", {"APP_ENV": "development"}) == "development"


def test_committed_env_examples_only_use_supported_keys():
    root = Path(__file__).resolve().parents[2]
    for relative_path in (".env.example", "infra/env/.env.example"):
        values = _MODULE.load_env_file(root / relative_path)
        errors = _MODULE._validate_known_keys(values)
        assert errors == [], f"{relative_path}: {errors}"


def test_runtime_env_accepts_explicit_previous_pilot_contract_registry():
    values = _complete_production_values()
    values["STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON"] = json.dumps(
        [
            {
                "product_id": "prod_Previous123",
                "price_id": "price_Previous123",
                "payment_link_id": "plink_Previous123",
                "payment_link_url": "https://buy.stripe.com/Previous123",
            }
        ]
    )

    assert validate_runtime_env(values, target_env="production") == []


@pytest.mark.parametrize(
    "raw_value",
    (
        "not-json",
        "{}",
        '[{"payment_link_id":"plink_Previous123"}]',
        json.dumps(
            [
                {
                    "product_id": "prod_Previous123",
                    "price_id": "price_Previous123",
                    "payment_link_id": "plink_test123",
                    "payment_link_url": "https://buy.stripe.com/Previous123",
                }
            ]
        ),
    ),
)
def test_runtime_env_rejects_invalid_previous_pilot_contract_registry(raw_value):
    values = _complete_production_values()
    values["STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON"] = raw_value

    errors = validate_runtime_env(values, target_env="production")

    assert any("STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON" in error for error in errors)


@pytest.mark.parametrize(
    ("overrides", "expected_key"),
    (
        ({"STRIPE_CREDIT_PRICE_ID": "price_Valid123"}, "STRIPE_CREDIT_PACK_SIZE"),
        (
            {
                "STRIPE_CREDIT_PRICE_ID": "price_Valid123",
                "STRIPE_CREDIT_PACK_SIZE": "25",
                "STRIPE_CREDIT_UNIT_AMOUNT": "400",
                "STRIPE_CREDIT_CURRENCY": "USD",
            },
            "STRIPE_CREDIT_CURRENCY",
        ),
    ),
)
def test_runtime_env_rejects_partial_or_invalid_credit_contract(
    overrides,
    expected_key,
):
    values = _complete_production_values()
    values.update(overrides)

    errors = validate_runtime_env(values, target_env="production")

    assert any(expected_key in error for error in errors)
