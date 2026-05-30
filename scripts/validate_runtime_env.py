from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys


_PLACEHOLDER_TOKENS = ("CHANGE_ME", "REPLACE_ME", "REPLACE_WITH", "GENERATE_WITH")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_SENSITIVE_PATTERNS = (
    r"(sk|pk|whsec)_[A-Za-z0-9_\.\-]+",
    r"postgres(?:ql)?://[^:]+:[^@]+@",
    r"redis://[^:]+:[^@]+@",
)
_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("JWT_SECRET_KEY", "JWT_SECRET", "SECRET_KEY"),
    ("STRIPE_PUBLIC_KEY", "STRIPE_PUBLISHABLE_KEY"),
    ("TURNSTILE_SITE_KEY", "NEXT_PUBLIC_TURNSTILE_SITE_KEY"),
    ("ADMIN_ALLOWED_IPS_RAW", "ADMIN_ALLOWED_IPS", "ADMIN_ALLOWED_IP"),
    ("PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW", "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS"),
)
_KNOWN_ENV_KEYS = {
    "ACME_EMAIL",
    "ADMIN_ALLOWED_IP",
    "ADMIN_ALLOWED_IPS",
    "ADMIN_ALLOWED_IPS_RAW",
    "ADMIN_PORT",
    "AI_ORCHESTRATOR_PORT",
    "ALLOWED_ORIGINS_RAW",
    "API_URL",
    "API_BASE_URL",
    "API_HOST",
    "API_PORT",
    "ADMIN_URL",
    "AGENTS_ENABLED",
    "AI_MODEL",
    "APP_DOMAIN",
    "APP_ENV",
    "APP_NAME",
    "APP_REGION",
    "APP_RUNTIME_ENV_FILE",
    "APP_URL",
    "APP_VERSION",
    "AUDIT_LOG_ENABLED",
    "BOTS_ENABLED",
    "CHAOS_ENABLED",
    "DATABASE_URL",
    "DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION",
    "DOMAIN",
    "ENABLE_SCRAPE_PROXY",
    "GRAFANA_ADMIN_USER",
    "GRAFANA_ADMIN_PASSWORD",
    "JWT_ACCESS_EXPIRE_MINUTES",
    "JWT_ALGORITHM",
    "JWT_AUDIENCE",
    "JWT_ISSUER",
    "JWT_REFRESH_EXPIRE_DAYS",
    "JWT_SECRET",
    "JWT_SECRET_KEY",
    "JWT_SECRET_KEY_REF",
    "LOG_LEVEL",
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED",
    "OLLAMA_ADMIN_BASE_URL",
    "OLLAMA_CLIENT_BASE_URL",
    "OLLAMA_DEFAULT_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_API_KEY_REF",
    "OPENAI_COST_GUARD_ENABLED",
    "OPENAI_MAX_MONTHLY_COST_USD",
    "OPENAI_TARGET_GROSS_MARGIN_PCT",
    "ORCHESTRATOR_ENABLED",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PASSWORD",
    "POSTGRES_PASSWORD_REF",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "MEMORY_ENABLED",
    "PRIVATE_ADMIN_URL",
    "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS",
    "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW",
    "PRIVATE_ORCHESTRATOR_ENABLED",
    "PRIVATE_ORCHESTRATOR_UPSTREAM_URL",
    "PUBLIC_IP",
    "PUBLIC_WEB_URL",
    "RATE_LIMIT_PER_MINUTE",
    "RATE_LIMIT_MAX_PER_DOMAIN",
    "REDIS_PASSWORD",
    "REDIS_PASSWORD_REF",
    "REDIS_URL",
    "RESEND_API_KEY",
    "RESEND_API_KEY_REF",
    "RESEND_FROM_EMAIL",
    "RESEND_FROM_NAME",
    "SECRET_KEY",
    "SECRET_PROVIDER",
    "SCRAPING_CLIENT_MAX_QUEUED_JOBS",
    "SCRAPING_ALLOWLIST_RAW",
    "SCRAPING_ALLOWED_CONTENT_TYPES_RAW",
    "SCRAPING_BROWSER_POOL_SIZE",
    "SCRAPING_CACHE_TTL_SECONDS",
    "SCRAPING_CIRCUIT_FAIL_THRESHOLD",
    "SCRAPING_CIRCUIT_OPEN_SECONDS",
    "SCRAPING_CLIENT_DAILY_QUOTA",
    "SCRAPING_DEDUPE_TTL_SECONDS",
    "SCRAPING_ENABLED",
    "SCRAPING_FEATURE_ASYNC_QUEUE_ENABLED",
    "SCRAPING_FEATURE_BROWSER_ENABLED",
    "SCRAPING_FEATURE_CACHE_FALLBACK_ENABLED",
    "SCRAPING_FEATURE_PROXY_ENABLED",
    "SCRAPING_JITTER_MAX_MS",
    "SCRAPING_JITTER_MIN_MS",
    "SCRAPING_JOB_TTL_SECONDS",
    "SCRAPING_MAX_REDIRECTS",
    "SCRAPING_MAX_RESPONSE_BYTES",
    "SCRAPING_MODE_DEFAULT",
    "SCRAPING_PROXY_BYPASS_DOMAINS_RAW",
    "SCRAPING_PROXY_HEALTH_CHECK_INTERVAL_SECONDS",
    "SCRAPING_PROXY_HEALTH_CHECK_URL",
    "SCRAPING_PROXY_LIST_RAW",
    "SCRAPING_PROXY_ROTATION_ENABLED",
    "SCRAPING_QUEUE_MAX_DEPTH",
    "SCRAPING_RATE_LIMIT_PER_DOMAIN_PER_MIN",
    "SCRAPING_REQUIRE_AUTH",
    "SCRAPING_RETRY_BACKOFF_BASE_MS",
    "SCRAPING_RETRY_MAX_ATTEMPTS",
    "SCRAPING_RUN_WORKER_IN_API",
    "SCRAPING_STRICT_ALLOWLIST",
    "SCRAPING_STEALTH_HEADER_ROTATION",
    "SCRAPING_STEALTH_MODE",
    "SCRAPING_STEALTH_PROFILE",
    "SCRAPING_STEALTH_TIMEZONE",
    "SCRAPING_STEALTH_VIEWPORT_HEIGHT",
    "SCRAPING_STEALTH_VIEWPORT_WIDTH",
    "SCRAPING_TIMEOUT_SECONDS",
    "SCRAPING_WORKER_HEARTBEAT_INTERVAL_SECONDS",
    "SCRAPING_WORKER_HEARTBEAT_TTL_SECONDS",
    "SCRAPE_MAX_RETRIES",
    "SCRAPE_TIMEOUT_MS",
    "SCRAPE_TTL_SECONDS",
    "STAGING_ADMIN_PORT",
    "STAGING_AI_PORT",
    "STAGING_API_PORT",
    "STAGING_BIND_ADDRESS",
    "STAGING_WEB_PORT",
    "SUPER_ADMIN_EMAIL",
    "STRIPE_CREDIT_PACK_SIZE",
    "STRIPE_CREDIT_PRICE_ID",
    "STRIPE_MODE",
    "STRIPE_PRICE_ADDON_API_PACK",
    "STRIPE_PRICE_ADDON_STORAGE_10GB",
    "STRIPE_PRICE_BUSINESS_MONTHLY_ID",
    "STRIPE_PRICE_BUSINESS_YEARLY_ID",
    "STRIPE_PRICE_CREDITS_PACK",
    "STRIPE_PRICE_MODULE_CONTENT",
    "STRIPE_PRICE_MODULE_DECISION",
    "STRIPE_PRICE_MODULE_EXECUTION",
    "STRIPE_PRICE_MODULE_GHOST",
    "STRIPE_PRICE_MODULE_KNOWLEDGE",
    "STRIPE_PRICE_MODULE_LEVERAGE",
    "STRIPE_PRICE_MODULE_MICRO_SAAS",
    "STRIPE_PRICE_MODULE_OFFER",
    "STRIPE_PRICE_MODULE_OPERATOR",
    "STRIPE_PRICE_MODULE_REVERSE",
    "STRIPE_PRICE_STARTER_MONTHLY_ID",
    "STRIPE_PRICE_PRO_MONTHLY_ID",
    "STRIPE_PRICE_PRO_YEARLY_ID",
    "STRIPE_PUBLIC_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_SECRET_KEY_REF",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_WEBHOOK_SECRET_REF",
    "TURNSTILE_ALLOWED_HOSTNAMES_RAW",
    "TURNSTILE_ENABLED",
    "TURNSTILE_PROTECT_BILLING",
    "TURNSTILE_PROTECT_CONTACT",
    "TURNSTILE_PROTECT_LOGIN",
    "TURNSTILE_PROTECT_REGISTER",
    "TURNSTILE_SECRET_KEY",
    "TURNSTILE_SECRET_KEY_REF",
    "TURNSTILE_SITEVERIFY_URL",
    "TURNSTILE_SITE_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN_REF",
    "TELEGRAM_CHAT_ID",
    "TOTP_ENCRYPTION_KEY",
    "TOTP_ENCRYPTION_KEY_REF",
    "VAULT_ADDR",
    "VAULT_REQUEST_TIMEOUT_SECONDS",
    "VAULT_TOKEN",
    "WEB_PORT",
    "NEXT_PUBLIC_TURNSTILE_SITE_KEY",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ZONE_ID",
    "CLOUDFLARE_ACCOUNT_ID",
    "OVH_ENDPOINT",
    "OVH_APPLICATION_KEY",
    "OVH_APPLICATION_SECRET",
    "OVH_CONSUMER_KEY",
    "OVH_SERVICE_NAME",
    "SANDBOX_ALLOW_LIVE_KEYS",
}


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        sanitized_value = re.sub(r"\s+#.*$", "", value).strip()
        values[key.strip()] = sanitized_value
    return values


def _looks_placeholder(value: str) -> bool:
    normalized = value.strip().upper()
    return not normalized or any(token in normalized for token in _PLACEHOLDER_TOKENS)


def _first_present(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = values.get(key, "").strip()
        if value:
            return value
    return ""


def _is_loopback_host(value: str) -> bool:
    host = value.strip().lower()
    return host in _LOOPBACK_HOSTS


def _validate_known_keys(values: dict[str, str]) -> list[str]:
    return [f"Unknown env key: {key}" for key in sorted(values) if key not in _KNOWN_ENV_KEYS]


def _validate_alias_conflicts(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for aliases in _ALIAS_GROUPS:
        present = {key: values[key].strip() for key in aliases if values.get(key, "").strip()}
        normalized_values = {value for value in present.values()}
        if len(normalized_values) > 1:
            errors.append(
                "Conflicting alias values for "
                + "/".join(aliases)
                + ": "
                + ", ".join(f"{key}={value}" for key, value in present.items())
            )
    return errors


def _validate_http_urlish(values: dict[str, str], key: str, errors: list[str]) -> None:
    value = values.get(key, "").strip()
    if not value or _looks_placeholder(value):
        return
    if not value.startswith(("http://", "https://")):
        errors.append(f"{key} must start with http:// or https://")


def _validate_secret_reference(
    values: dict[str, str],
    *,
    secret_key: str,
    ref_key: str,
    errors: list[str],
) -> bool:
    reference = values.get(ref_key, "").strip()
    direct_value = values.get(secret_key, "").strip()
    active_ref = reference or (direct_value if direct_value.startswith("vault://") else "")
    if not active_ref:
        return False
    if not active_ref.startswith("vault://"):
        errors.append(f"{ref_key} must use vault://<mount>/<path>#<field>")
        return True
    if "#" not in active_ref:
        errors.append(f"{ref_key} must include a #field suffix")
    return True


def _require_value(
    errors: list[str],
    values: dict[str, str],
    key: str,
    *,
    aliases: tuple[str, ...] = (),
    allow_placeholders: bool = False,
    min_length: int | None = None,
    message: str | None = None,
) -> str:
    value = _first_present(values, key, *aliases)
    if not value:
        errors.append(message or f"Missing required key: {key}")
        return ""
    if not allow_placeholders and _looks_placeholder(value):
        errors.append(message or f"{key} must be set to a non-placeholder value")
        return value
    if min_length is not None and not allow_placeholders and len(value) < min_length:
        errors.append(message or f"{key} must be at least {min_length} characters")
    return value


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SENSITIVE_PATTERNS:
        redacted = re.sub(pattern, "[REDACTED]", redacted)
    return redacted


def resolve_target_env(file_path: str, values: dict[str, str]) -> str:
    if file_path.endswith(".env.dev.example"):
        return "development"
    if file_path.endswith(".env.staging.example"):
        return "staging"
    if file_path.endswith(".env.example") and "infra/env" in file_path:
        return "production"
    return values.get("APP_ENV", "development").strip() or "development"


def validate_runtime_env(
    values: dict[str, str],
    *,
    target_env: str,
    allow_placeholders: bool = False,
) -> list[str]:
    errors: list[str] = []
    if target_env not in {"development", "staging", "production", "sandbox"}:
        return [f"Unsupported target environment: {target_env}"]

    errors.extend(_validate_known_keys(values))
    errors.extend(_validate_alias_conflicts(values))

    app_env = values.get("APP_ENV", "").strip()
    if app_env != target_env:
        errors.append(f"APP_ENV must be '{target_env}' (got {app_env or '<empty>'})")

    _require_value(
        errors,
        values,
        "DATABASE_URL",
        allow_placeholders=allow_placeholders,
        message="DATABASE_URL is required",
    )
    _require_value(
        errors,
        values,
        "REDIS_URL",
        allow_placeholders=allow_placeholders,
        message="REDIS_URL is required",
    )
    jwt_secret_reference = values.get("JWT_SECRET_KEY_REF", "").strip()
    jwt_secret_direct = _first_present(values, "JWT_SECRET_KEY", "JWT_SECRET", "SECRET_KEY")
    if not jwt_secret_reference and not jwt_secret_direct.startswith("vault://"):
        _require_value(
            errors,
            values,
            "JWT_SECRET_KEY",
            aliases=("JWT_SECRET", "SECRET_KEY"),
            allow_placeholders=allow_placeholders,
            min_length=32,
            message="JWT secret must be set to a non-placeholder value with at least 32 characters",
        )

    secret_ref_enabled = False
    for secret_key, ref_key in (
        ("JWT_SECRET_KEY", "JWT_SECRET_KEY_REF"),
        ("POSTGRES_PASSWORD", "POSTGRES_PASSWORD_REF"),
        ("REDIS_PASSWORD", "REDIS_PASSWORD_REF"),
        ("STRIPE_SECRET_KEY", "STRIPE_SECRET_KEY_REF"),
        ("STRIPE_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET_REF"),
        ("TURNSTILE_SECRET_KEY", "TURNSTILE_SECRET_KEY_REF"),
        ("TOTP_ENCRYPTION_KEY", "TOTP_ENCRYPTION_KEY_REF"),
        ("RESEND_API_KEY", "RESEND_API_KEY_REF"),
        ("OPENAI_API_KEY", "OPENAI_API_KEY_REF"),
        ("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN_REF"),
    ):
        secret_ref_enabled = _validate_secret_reference(
            values,
            secret_key=secret_key,
            ref_key=ref_key,
            errors=errors,
        ) or secret_ref_enabled

    for key in (
        "APP_URL",
        "ADMIN_URL",
        "API_URL",
        "API_BASE_URL",
        "PUBLIC_WEB_URL",
        "PRIVATE_ADMIN_URL",
        "PRIVATE_ORCHESTRATOR_UPSTREAM_URL",
        "OLLAMA_CLIENT_BASE_URL",
        "OLLAMA_ADMIN_BASE_URL",
        "VAULT_ADDR",
        "TURNSTILE_SITEVERIFY_URL",
    ):
        _validate_http_urlish(values, key, errors)

    secret_provider = values.get("SECRET_PROVIDER", "auto").strip() or "auto"
    if secret_provider not in {"env", "auto", "vault"}:
        errors.append("SECRET_PROVIDER must be one of env, auto, vault")
    if secret_provider == "vault" or secret_ref_enabled:
        _require_value(
            errors,
            values,
            "VAULT_ADDR",
            allow_placeholders=allow_placeholders,
            message="VAULT_ADDR is required when Vault-managed secrets are enabled",
        )
        _require_value(
            errors,
            values,
            "VAULT_TOKEN",
            allow_placeholders=allow_placeholders,
            message="VAULT_TOKEN is required when Vault-managed secrets are enabled",
        )

    stripe_secret = _first_present(values, "STRIPE_SECRET_KEY")
    stripe_public = _first_present(values, "STRIPE_PUBLIC_KEY", "STRIPE_PUBLISHABLE_KEY")
    stripe_webhook = _first_present(values, "STRIPE_WEBHOOK_SECRET")
    turnstile_site_key = _first_present(values, "TURNSTILE_SITE_KEY", "NEXT_PUBLIC_TURNSTILE_SITE_KEY")
    turnstile_secret = _first_present(values, "TURNSTILE_SECRET_KEY")
    turnstile_enabled = values.get("TURNSTILE_ENABLED", "").strip().lower() == "true"
    stripe_secret_ref = values.get("STRIPE_SECRET_KEY_REF", "").strip()
    stripe_webhook_ref = values.get("STRIPE_WEBHOOK_SECRET_REF", "").strip()
    turnstile_secret_ref = values.get("TURNSTILE_SECRET_KEY_REF", "").strip()
    totp_ref = values.get("TOTP_ENCRYPTION_KEY_REF", "").strip()
    stripe_live_secret_prefix = "sk" + "_live_"
    stripe_live_public_prefix = "pk" + "_live_"
    stripe_webhook_prefix = "wh" + "sec_"

    if target_env == "development":
        if stripe_secret.startswith(stripe_live_secret_prefix):
            errors.append("Development refuses live Stripe secret keys")
        if stripe_public.startswith(stripe_live_public_prefix):
            errors.append("Development refuses live Stripe public keys")
        return errors

    if target_env == "sandbox":
        stripe_mode = values.get("STRIPE_MODE", "").strip().lower()
        if stripe_mode and stripe_mode != "test":
            errors.append("Sandbox requires STRIPE_MODE=test")
        if stripe_secret.startswith(stripe_live_secret_prefix):
            errors.append("Sandbox refuses live Stripe secret keys")
        if stripe_public.startswith(stripe_live_public_prefix):
            errors.append("Sandbox refuses live Stripe public keys")
        bind_address = values.get("STAGING_BIND_ADDRESS", "").strip()
        if bind_address and not _is_loopback_host(bind_address):
            errors.append("Sandbox requires STAGING_BIND_ADDRESS to stay loopback-only when provided")
        return errors

    if not totp_ref and not values.get("TOTP_ENCRYPTION_KEY", "").strip().startswith("vault://"):
        _require_value(
            errors,
            values,
            "TOTP_ENCRYPTION_KEY",
            allow_placeholders=allow_placeholders,
            message="TOTP_ENCRYPTION_KEY must be set to a non-placeholder Fernet key",
        )

    if target_env == "staging":
        bind_address = values.get("STAGING_BIND_ADDRESS", "127.0.0.1").strip()
        if not _is_loopback_host(bind_address):
            errors.append("Staging requires STAGING_BIND_ADDRESS to stay loopback-only")
        if stripe_secret.startswith(stripe_live_secret_prefix):
            errors.append("Staging refuses live Stripe keys")
        if stripe_public.startswith(stripe_live_public_prefix):
            errors.append("Staging refuses live Stripe public keys")
        if turnstile_enabled and not turnstile_site_key:
            errors.append("Staging TURNSTILE_ENABLED=true requires TURNSTILE_SITE_KEY/NEXT_PUBLIC_TURNSTILE_SITE_KEY")
        return errors

    if not stripe_secret and not stripe_secret_ref:
        errors.append("Production requires a live Stripe secret key")
    elif not stripe_secret_ref and not allow_placeholders and not stripe_secret.startswith(stripe_live_secret_prefix):
        errors.append("Production requires a live Stripe secret key")

    if not stripe_public:
        errors.append("Production requires a live Stripe public key")
    elif not allow_placeholders and not stripe_public.startswith(stripe_live_public_prefix):
        errors.append("Production requires a live Stripe public key")

    if not stripe_webhook and not stripe_webhook_ref:
        errors.append("Production requires a Stripe webhook signing secret")
    elif not stripe_webhook_ref and not allow_placeholders and not stripe_webhook.startswith(stripe_webhook_prefix):
        errors.append("Production requires a Stripe webhook signing secret")

    if turnstile_enabled:
        if not turnstile_site_key:
            errors.append("Production TURNSTILE_ENABLED=true requires TURNSTILE_SITE_KEY/NEXT_PUBLIC_TURNSTILE_SITE_KEY")
        if not turnstile_secret and not turnstile_secret_ref:
            errors.append("Production TURNSTILE_ENABLED=true requires TURNSTILE_SECRET_KEY")

    next_public_api_url = values.get("NEXT_PUBLIC_API_URL", "").strip()
    api_base_url = values.get("API_BASE_URL", "").strip()
    if next_public_api_url:
        if not next_public_api_url.startswith("https://"):
            errors.append("Production NEXT_PUBLIC_API_URL must use https:// when set")
        if "localhost" in next_public_api_url or "127.0.0.1" in next_public_api_url:
            errors.append("Production NEXT_PUBLIC_API_URL cannot include localhost/127.0.0.1")
        if api_base_url and not allow_placeholders and next_public_api_url != api_base_url:
            errors.append("Production NEXT_PUBLIC_API_URL must match API_BASE_URL when set")

    admin_allowlist = _first_present(values, "ADMIN_ALLOWED_IPS_RAW", "ADMIN_ALLOWED_IPS", "ADMIN_ALLOWED_IP")
    if not admin_allowlist:
        errors.append("Production requires ADMIN_ALLOWED_IPS/ADMIN_ALLOWED_IP to be configured")

    origins = values.get("ALLOWED_ORIGINS_RAW", "")
    if "localhost" in origins or "127.0.0.1" in origins:
        errors.append("Production ALLOWED_ORIGINS_RAW cannot include localhost/127.0.0.1")

    for key in ("API_BASE_URL", "PUBLIC_WEB_URL", "PRIVATE_ADMIN_URL"):
        value = values.get(key, "").strip()
        if value and ("localhost" in value or "127.0.0.1" in value):
            errors.append(f"Production {key} cannot include localhost/127.0.0.1")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deploy-time runtime env invariants.")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--target-env", required=True, choices=("development", "staging", "production", "sandbox"))
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Permit placeholder secrets for env templates instead of live runtime files.",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.is_file():
        print(f"❌ Missing env file: {env_path}", file=sys.stderr)
        return 1

    errors = validate_runtime_env(
        load_env_file(env_path),
        target_env=args.target_env,
        allow_placeholders=args.allow_placeholders,
    )
    if errors:
        print("❌ Runtime env validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {redact_text(error)}", file=sys.stderr)
        return 1

    print(f"✅ Runtime env validation passed for {args.target_env}: {env_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
