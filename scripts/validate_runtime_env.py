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
    "API_BASE_URL",
    "API_HOST",
    "API_PORT",
    "APP_ENV",
    "APP_NAME",
    "APP_RUNTIME_ENV_FILE",
    "APP_VERSION",
    "DATABASE_URL",
    "DOMAIN",
    "GRAFANA_ADMIN_PASSWORD",
    "JWT_ACCESS_EXPIRE_MINUTES",
    "JWT_ALGORITHM",
    "JWT_AUDIENCE",
    "JWT_ISSUER",
    "JWT_REFRESH_EXPIRE_DAYS",
    "JWT_SECRET",
    "JWT_SECRET_KEY",
    "LOG_LEVEL",
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED",
    "OLLAMA_ADMIN_BASE_URL",
    "OLLAMA_CLIENT_BASE_URL",
    "OLLAMA_DEFAULT_MODEL",
    "OPENAI_API_KEY",
    "POSTGRES_DB",
    "POSTGRES_PASSWORD",
    "POSTGRES_USER",
    "PRIVATE_ADMIN_URL",
    "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS",
    "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW",
    "PRIVATE_ORCHESTRATOR_ENABLED",
    "PRIVATE_ORCHESTRATOR_UPSTREAM_URL",
    "PUBLIC_IP",
    "PUBLIC_WEB_URL",
    "RATE_LIMIT_PER_MINUTE",
    "REDIS_PASSWORD",
    "REDIS_URL",
    "RESEND_API_KEY",
    "RESEND_FROM_EMAIL",
    "RESEND_FROM_NAME",
    "SECRET_KEY",
    "STAGING_ADMIN_PORT",
    "STAGING_AI_PORT",
    "STAGING_API_PORT",
    "STAGING_BIND_ADDRESS",
    "STAGING_WEB_PORT",
    "STRIPE_CREDIT_PACK_SIZE",
    "STRIPE_CREDIT_PRICE_ID",
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
    "STRIPE_WEBHOOK_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TOTP_ENCRYPTION_KEY",
    "VAULT_ADDR",
    "VAULT_TOKEN",
    "WEB_PORT",
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
    _require_value(
        errors,
        values,
        "JWT_SECRET_KEY",
        aliases=("JWT_SECRET", "SECRET_KEY"),
        allow_placeholders=allow_placeholders,
        min_length=32,
        message="JWT secret must be set to a non-placeholder value with at least 32 characters",
    )

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

    stripe_secret = _first_present(values, "STRIPE_SECRET_KEY")
    stripe_public = _first_present(values, "STRIPE_PUBLIC_KEY", "STRIPE_PUBLISHABLE_KEY")
    stripe_webhook = _first_present(values, "STRIPE_WEBHOOK_SECRET")

    if target_env == "development":
        if stripe_secret.startswith("sk_live_"):
            errors.append("Development refuses live Stripe secret keys")
        if stripe_public.startswith("pk_live_"):
            errors.append("Development refuses live Stripe public keys")
        return errors

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
        if stripe_secret.startswith("sk_live_"):
            errors.append("Staging refuses live Stripe keys")
        if stripe_public.startswith("pk_live_"):
            errors.append("Staging refuses live Stripe public keys")
        return errors

    if not stripe_secret:
        errors.append("Production requires STRIPE_SECRET_KEY=sk_live_...")
    elif not allow_placeholders and not stripe_secret.startswith("sk_live_"):
        errors.append("Production requires STRIPE_SECRET_KEY=sk_live_...")

    if not stripe_public:
        errors.append("Production requires STRIPE_PUBLIC_KEY=pk_live_...")
    elif not allow_placeholders and not stripe_public.startswith("pk_live_"):
        errors.append("Production requires STRIPE_PUBLIC_KEY=pk_live_...")

    if not stripe_webhook:
        errors.append("Production requires STRIPE_WEBHOOK_SECRET=whsec_...")
    elif not allow_placeholders and not stripe_webhook.startswith("whsec_"):
        errors.append("Production requires STRIPE_WEBHOOK_SECRET=whsec_...")

    if values.get("NEXT_PUBLIC_API_URL", "").strip():
        errors.append("Production requires NEXT_PUBLIC_API_URL to stay empty for same-origin /api")

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
