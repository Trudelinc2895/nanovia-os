from __future__ import annotations

import argparse
import ipaddress
import json
import re
from pathlib import Path
import sys
from urllib.parse import urlsplit


_PLACEHOLDER_TOKENS = ("CHANGE_ME", "REPLACE_ME", "REPLACE_WITH", "GENERATE_WITH")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_CANONICAL_RAW_KEYS = {"DOMAIN", "PUBLIC_WEB_URL"}
_RESERVED_DOMAIN_LABELS = {"example", "invalid", "localhost", "test"}
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_PILOT_PAYMENT_LINK_PATH = re.compile(r"^/[A-Za-z0-9_]+$")
_PRODUCTION_HTTPS_URL_KEYS = (
    "API_BASE_URL",
    "PUBLIC_WEB_URL",
    "PRIVATE_ADMIN_URL",
)
_SENSITIVE_PATTERNS = (
    r"(sk|pk|whsec)_[A-Za-z0-9_\.\-]+",
    r"postgres(?:ql)?://[^:]+:[^@]+@",
    r"redis://[^:]+:[^@]+@",
)
_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("JWT_SECRET_KEY", "JWT_SECRET", "SECRET_KEY"),
    ("STRIPE_PUBLIC_KEY", "STRIPE_PUBLISHABLE_KEY"),
    ("ADMIN_ALLOWED_IPS_RAW", "ADMIN_ALLOWED_IPS", "ADMIN_ALLOWED_IP"),
    ("PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW", "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS"),
)
_PILOT_FORMAT_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "CONTACT_RECIPIENT_EMAIL",
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        "must be a valid email address",
    ),
    (
        "STRIPE_ACCOUNT_ID",
        r"^acct_[A-Za-z0-9]+$",
        "must use the acct_... format",
    ),
    (
        "STRIPE_PILOT_PAYMENT_LINK_ID",
        r"^plink_[A-Za-z0-9]+$",
        "must use the plink_... format",
    ),
    (
        "STRIPE_PILOT_PRICE_ID",
        r"^price_[A-Za-z0-9]+$",
        "must use the price_... format",
    ),
    (
        "STRIPE_PILOT_PRODUCT_ID",
        r"^prod_[A-Za-z0-9]+$",
        "must use the prod_... format",
    ),
)
_PILOT_REQUIRED_KEYS = tuple(rule[0] for rule in _PILOT_FORMAT_RULES) + (
    "STRIPE_PILOT_PAYMENT_LINK_URL",
)
_KNOWN_ENV_KEYS = {
    "ACME_EMAIL",
    "ADMIN_ALLOWED_IP",
    "ADMIN_ALLOWED_IPS",
    "ADMIN_ALLOWED_IPS_RAW",
    "ADMIN_PORT",
    "AI_ORCHESTRATOR_PORT",
    "ALLOWED_ORIGINS_RAW",
    "API_BASE_URL",
    "API_HOST",
    "API_PORT",
    "APP_ENV",
    "APP_NAME",
    "APP_REGION",
    "APP_RUNTIME_ENV_FILE",
    "APP_VERSION",
    "CONTACT_RECIPIENT_EMAIL",
    "DATABASE_URL",
    "CHAOS_ENABLED",
    "DOMAIN",
    "ENABLE_SCRAPE_PROXY",
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
    "POSTGRES_DB",
    "POSTGRES_PASSWORD",
    "POSTGRES_PASSWORD_REF",
    "POSTGRES_USER",
    "PRIVATE_ADMIN_URL",
    "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS",
    "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW",
    "PRIVATE_ORCHESTRATOR_ENABLED",
    "PRIVATE_ORCHESTRATOR_UPSTREAM_URL",
    "PUBLIC_IP",
    "PUBLIC_WEB_URL",
    "RATE_LIMIT_MAX_PER_DOMAIN",
    "RATE_LIMIT_PER_MINUTE",
    "REDIS_PASSWORD",
    "REDIS_PASSWORD_REF",
    "REDIS_URL",
    "RESEND_API_KEY",
    "RESEND_API_KEY_REF",
    "RESEND_FROM_EMAIL",
    "RESEND_FROM_NAME",
    "SCRAPE_MAX_RETRIES",
    "SCRAPE_TIMEOUT_MS",
    "SCRAPE_TTL_SECONDS",
    "SCRAPING_ALLOWED_CONTENT_TYPES_RAW",
    "SCRAPING_ALLOWLIST_RAW",
    "SCRAPING_BROWSER_POOL_SIZE",
    "SCRAPING_CACHE_TTL_SECONDS",
    "SCRAPING_CIRCUIT_FAIL_THRESHOLD",
    "SCRAPING_CIRCUIT_OPEN_SECONDS",
    "SCRAPING_CLIENT_DAILY_QUOTA",
    "SCRAPING_DEDUPE_TTL_SECONDS",
    "SCRAPING_ENABLED",
    "SCRAPING_JITTER_MAX_MS",
    "SCRAPING_JITTER_MIN_MS",
    "SCRAPING_JOB_TTL_SECONDS",
    "SCRAPING_MAX_REDIRECTS",
    "SCRAPING_MAX_RESPONSE_BYTES",
    "SCRAPING_MODE_DEFAULT",
    "SCRAPING_PROXY_LIST_RAW",
    "SCRAPING_PROXY_ROTATION_ENABLED",
    "SCRAPING_QUEUE_MAX_DEPTH",
    "SCRAPING_RATE_LIMIT_PER_DOMAIN_PER_MIN",
    "SCRAPING_REQUIRE_AUTH",
    "SCRAPING_RETRY_BACKOFF_BASE_MS",
    "SCRAPING_RETRY_MAX_ATTEMPTS",
    "SCRAPING_RUN_WORKER_IN_API",
    "SCRAPING_STEALTH_MODE",
    "SCRAPING_STRICT_ALLOWLIST",
    "SCRAPING_TIMEOUT_SECONDS",
    "SECRET_KEY",
    "SECRET_PROVIDER",
    "STAGING_ADMIN_PORT",
    "STAGING_AI_PORT",
    "STAGING_API_PORT",
    "STAGING_BIND_ADDRESS",
    "STAGING_WEB_PORT",
    "STRIPE_CREDIT_PACK_SIZE",
    "STRIPE_CREDIT_CURRENCY",
    "STRIPE_CREDIT_PRICE_ID",
    "STRIPE_CREDIT_UNIT_AMOUNT",
    "STRIPE_ACCOUNT_ID",
    "STRIPE_PILOT_PAYMENT_LINK_ID",
    "STRIPE_PILOT_PAYMENT_LINK_URL",
    "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON",
    "STRIPE_PILOT_PRICE_ID",
    "STRIPE_PILOT_PRODUCT_ID",
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
    "STRIPE_PRICE_PRO_MONTHLY_ID",
    "STRIPE_PRICE_PRO_YEARLY_ID",
    "STRIPE_PUBLIC_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_SECRET_KEY_REF",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_WEBHOOK_SECRET_REF",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN_REF",
    "TELEGRAM_CHAT_ID",
    "TOTP_ENCRYPTION_KEY",
    "TOTP_ENCRYPTION_KEY_REF",
    "VAULT_ADDR",
    "VAULT_REQUEST_TIMEOUT_SECONDS",
    "VAULT_TOKEN",
    "WEB_PORT",
}


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = raw_line.split("=", 1)
        normalized_key = key.strip()
        sanitized_value = re.sub(r"\s+#.*$", "", value)
        values[normalized_key] = (
            sanitized_value
            if normalized_key in _CANONICAL_RAW_KEYS
            else sanitized_value.strip()
        )
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


def _validate_pilot_formats(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for key, pattern, message in _PILOT_FORMAT_RULES:
        value = values.get(key, "").strip()
        if not value or _looks_placeholder(value):
            continue
        if re.fullmatch(pattern, value) is None:
            errors.append(f"{key} {message}")
    return errors


def _validate_pilot_payment_link_url(
    values: dict[str, str],
    *,
    target_env: str,
) -> list[str]:
    key = "STRIPE_PILOT_PAYMENT_LINK_URL"
    raw_value = values.get(key, "")
    value = raw_value.strip()
    if not value or _looks_placeholder(value):
        return []
    message = f"{key} must use a canonical https://buy.stripe.com/... URL"
    if raw_value != value:
        return [message]
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return [message]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "buy.stripe.com"
        or parsed.netloc not in {"buy.stripe.com", "buy.stripe.com:443"}
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or _PILOT_PAYMENT_LINK_PATH.fullmatch(parsed.path) is None
        or parsed.query
        or parsed.fragment
        or (target_env == "production" and parsed.path.lstrip("/").startswith("test_"))
    ):
        return [message]
    return []


def _validate_previous_pilot_contracts(
    values: dict[str, str],
    *,
    target_env: str,
) -> list[str]:
    key = "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON"
    raw_value = values.get(key, "[]").strip()
    if not raw_value or _looks_placeholder(raw_value):
        return []
    try:
        contracts = json.loads(raw_value)
    except (TypeError, ValueError):
        return [f"{key} must be a valid JSON list"]
    if not isinstance(contracts, list):
        return [f"{key} must be a valid JSON list"]
    expected_keys = {"product_id", "price_id", "payment_link_id", "payment_link_url"}
    errors: list[str] = []
    payment_link_ids = {values.get("STRIPE_PILOT_PAYMENT_LINK_ID", "").strip()}
    payment_link_urls = {values.get("STRIPE_PILOT_PAYMENT_LINK_URL", "").strip()}
    patterns = {
        "product_id": r"^prod_[A-Za-z0-9]+$",
        "price_id": r"^price_[A-Za-z0-9]+$",
        "payment_link_id": r"^plink_[A-Za-z0-9]+$",
    }
    for index, contract_value in enumerate(contracts):
        label = f"{key}[{index}]"
        if not isinstance(contract_value, dict) or set(contract_value) != expected_keys:
            errors.append(f"{label} must contain exactly the Pilot contract keys")
            continue
        for field_name, pattern in patterns.items():
            field_value = contract_value.get(field_name)
            if not isinstance(field_value, str) or re.fullmatch(pattern, field_value) is None:
                errors.append(f"{label}.{field_name} has an invalid format")
        link_id = contract_value.get("payment_link_id")
        link_url = contract_value.get("payment_link_url")
        if isinstance(link_id, str):
            if link_id in payment_link_ids:
                errors.append(f"{label}.payment_link_id is duplicated")
            payment_link_ids.add(link_id)
        url_errors = _validate_pilot_payment_link_url(
            {"STRIPE_PILOT_PAYMENT_LINK_URL": link_url if isinstance(link_url, str) else ""},
            target_env=target_env,
        )
        if url_errors:
            errors.append(f"{label}.payment_link_url is invalid")
        elif isinstance(link_url, str):
            normalized_url = link_url.replace("buy.stripe.com:443", "buy.stripe.com")
            normalized_existing = {
                value.replace("buy.stripe.com:443", "buy.stripe.com")
                for value in payment_link_urls
            }
            if normalized_url in normalized_existing:
                errors.append(f"{label}.payment_link_url is duplicated")
            payment_link_urls.add(link_url)
    return errors


def _validate_credit_contract(
    values: dict[str, str],
    *,
    allow_placeholders: bool,
) -> list[str]:
    keys = (
        "STRIPE_CREDIT_PRICE_ID",
        "STRIPE_CREDIT_PACK_SIZE",
        "STRIPE_CREDIT_UNIT_AMOUNT",
        "STRIPE_CREDIT_CURRENCY",
    )
    raw_values = {key: values.get(key, "").strip() for key in keys}
    price_id = raw_values["STRIPE_CREDIT_PRICE_ID"]
    placeholder_price = _looks_placeholder(price_id) or "..." in price_id
    if (
        (not price_id or (allow_placeholders and placeholder_price))
        and raw_values["STRIPE_CREDIT_UNIT_AMOUNT"] in {"", "0"}
        and not raw_values["STRIPE_CREDIT_CURRENCY"]
    ):
        return []

    errors: list[str] = []
    if re.fullmatch(r"^price_[A-Za-z0-9]+$", price_id) is None:
        errors.append("STRIPE_CREDIT_PRICE_ID must use the price_... format")
    for key in ("STRIPE_CREDIT_PACK_SIZE", "STRIPE_CREDIT_UNIT_AMOUNT"):
        try:
            numeric_value = int(raw_values[key])
        except ValueError:
            numeric_value = 0
        if numeric_value <= 0 or str(numeric_value) != raw_values[key]:
            errors.append(f"{key} must be a positive integer")
    if re.fullmatch(r"[a-z]{3}", raw_values["STRIPE_CREDIT_CURRENCY"]) is None:
        errors.append("STRIPE_CREDIT_CURRENCY must be a lowercase ISO currency code")
    return errors


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


def _is_canonical_dns_name(value: str) -> bool:
    if (
        not value
        or value != value.strip()
        or value != value.lower()
        or len(value) > 253
        or value.endswith(".")
        or any(character.isspace() for character in value)
        or "*" in value
        or _looks_placeholder(value)
    ):
        return False
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        return False
    labels = value.split(".")
    return (
        len(labels) >= 2
        and not _RESERVED_DOMAIN_LABELS.intersection(labels)
        and all(_DNS_LABEL.fullmatch(label) is not None for label in labels)
    )


def _validate_production_public_host(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    domain = values.get("DOMAIN", "")
    domain_valid = _is_canonical_dns_name(domain)
    if not domain:
        errors.append("Production DOMAIN is required")
    elif not domain_valid:
        errors.append("Production DOMAIN must be a canonical DNS hostname")

    public_web_url = values.get("PUBLIC_WEB_URL", "")
    if not public_web_url:
        errors.append("Production PUBLIC_WEB_URL is required")
        return errors
    try:
        parsed = urlsplit(public_web_url)
        port = parsed.port
    except ValueError:
        parsed = None
        port = None
    valid_url = (
        parsed is not None
        and public_web_url == public_web_url.strip()
        and not any(character.isspace() for character in public_web_url)
        and parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and parsed.path == ""
        and not parsed.query
        and not parsed.fragment
        and domain_valid
        and parsed.hostname == domain
        and parsed.netloc in {domain, f"{domain}:443"}
    )
    if not valid_url:
        errors.append(
            "Production PUBLIC_WEB_URL must be the canonical HTTPS URL for DOMAIN"
        )
    return errors


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
    if target_env not in {"development", "staging", "production"}:
        return [f"Unsupported target environment: {target_env}"]

    errors.extend(_validate_known_keys(values))
    errors.extend(_validate_pilot_formats(values))
    errors.extend(_validate_pilot_payment_link_url(values, target_env=target_env))
    errors.extend(_validate_previous_pilot_contracts(values, target_env=target_env))
    errors.extend(
        _validate_credit_contract(values, allow_placeholders=allow_placeholders)
    )
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
        "API_BASE_URL",
        "PUBLIC_WEB_URL",
        "PRIVATE_ADMIN_URL",
        "PRIVATE_ORCHESTRATOR_UPSTREAM_URL",
        "OLLAMA_CLIENT_BASE_URL",
        "OLLAMA_ADMIN_BASE_URL",
        "VAULT_ADDR",
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
    stripe_secret_ref = values.get("STRIPE_SECRET_KEY_REF", "").strip()
    stripe_webhook_ref = values.get("STRIPE_WEBHOOK_SECRET_REF", "").strip()
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
        return errors

    errors.extend(_validate_production_public_host(values))

    if not allow_placeholders:
        for key in _PILOT_REQUIRED_KEYS:
            _require_value(
                errors,
                values,
                key,
                message=f"{key} is required in production",
            )

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

    if values.get("NEXT_PUBLIC_API_URL", "").strip():
        errors.append("Production requires NEXT_PUBLIC_API_URL to stay empty for same-origin /api")

    admin_allowlist = _first_present(values, "ADMIN_ALLOWED_IPS_RAW", "ADMIN_ALLOWED_IPS", "ADMIN_ALLOWED_IP")
    if not admin_allowlist:
        errors.append("Production requires ADMIN_ALLOWED_IPS/ADMIN_ALLOWED_IP to be configured")

    origins = values.get("ALLOWED_ORIGINS_RAW", "")
    if "localhost" in origins or "127.0.0.1" in origins:
        errors.append("Production ALLOWED_ORIGINS_RAW cannot include localhost/127.0.0.1")

    for key in _PRODUCTION_HTTPS_URL_KEYS:
        raw_value = values.get(key, "")
        value = raw_value.strip()
        if (
            value
            and not _looks_placeholder(value)
            and (raw_value != value or not value.startswith("https://"))
        ):
            errors.append(f"Production {key} must use https://")
        if value and ("localhost" in value or "127.0.0.1" in value):
            errors.append(f"Production {key} cannot include localhost/127.0.0.1")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deploy-time runtime env invariants.")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--target-env", required=True, choices=("development", "staging", "production"))
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
