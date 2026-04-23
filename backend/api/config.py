"""backend/api/config.py — settings via env"""
from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.core.secret_manager import resolve_secret_value


_PLACEHOLDER_TOKENS = ("CHANGE_ME", "REPLACE_ME", "REPLACE_WITH", "GENERATE_WITH")
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _looks_placeholder(value: str) -> bool:
    upper = value.strip().upper()
    return not upper or any(token in upper for token in _PLACEHOLDER_TOKENS)


class Settings(BaseSettings):
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_NAME: str = "Nanovia OS"
    APP_VERSION: str = "1.0.0"
    DOMAIN: str = "nanovia.ca"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    APP_RUNTIME_ENV_FILE: str = "../.env"
    ACME_EMAIL: str = "admin@nanovia.ca"
    PUBLIC_IP: str = ""

    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8010
    ADMIN_PORT: int = 3020
    WEB_PORT: int = 3000
    AI_ORCHESTRATOR_PORT: int = 8020
    API_BASE_URL: str = "http://127.0.0.1:8010"
    PUBLIC_WEB_URL: str = "http://127.0.0.1:3000"
    PRIVATE_ADMIN_URL: str = "http://127.0.0.1:3020"
    PRIVATE_ORCHESTRATOR_ENABLED: bool = False
    NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED: bool = False
    PRIVATE_ORCHESTRATOR_UPSTREAM_URL: str = "http://ai-orchestrator:8020"
    PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW: str = Field(
        default="operator,ghost_agency,decision_engine",
        validation_alias=AliasChoices(
            "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW",
            "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS",
        ),
    )
    ADMIN_ALLOWED_IPS_RAW: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_ALLOWED_IPS_RAW", "ADMIN_ALLOWED_IPS", "ADMIN_ALLOWED_IP"),
    )

    DATABASE_URL: str
    POSTGRES_DB: str = ""
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""
    SECRET_PROVIDER: Literal["env", "auto", "vault"] = "auto"
    VAULT_ADDR: str = "http://127.0.0.1:8200"
    VAULT_TOKEN: str = ""
    VAULT_REQUEST_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    JWT_SECRET_KEY_REF: str = ""
    POSTGRES_PASSWORD_REF: str = ""
    REDIS_PASSWORD_REF: str = ""

    JWT_SECRET_KEY: str = Field(
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET", "SECRET_KEY")
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_EXPIRE_DAYS: int = 30
    JWT_ISSUER: str = "nanovia"
    JWT_AUDIENCE: str = "nanovia-users"

    STRIPE_PUBLIC_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("STRIPE_PUBLIC_KEY", "STRIPE_PUBLISHABLE_KEY"),
    )
    STRIPE_SECRET_KEY_REF: str = ""
    STRIPE_WEBHOOK_SECRET_REF: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_PRO_MONTHLY_ID: str = ""
    STRIPE_PRICE_PRO_YEARLY_ID: str = ""
    STRIPE_PRICE_BUSINESS_MONTHLY_ID: str = ""
    STRIPE_PRICE_BUSINESS_YEARLY_ID: str = ""
    STRIPE_CREDIT_PRICE_ID: str = ""
    STRIPE_CREDIT_PACK_SIZE: int = Field(default=100, ge=1)
    STRIPE_PRICE_ADDON_API_PACK: str = ""
    STRIPE_PRICE_ADDON_STORAGE_10GB: str = ""
    STRIPE_PRICE_CREDITS_PACK: str = ""

    # Per-module à-la-carte prices (optional — set in Stripe dashboard)
    STRIPE_PRICE_MODULE_OPERATOR: str = ""
    STRIPE_PRICE_MODULE_CONTENT: str = ""
    STRIPE_PRICE_MODULE_MICRO_SAAS: str = ""
    STRIPE_PRICE_MODULE_GHOST: str = ""
    STRIPE_PRICE_MODULE_DECISION: str = ""
    STRIPE_PRICE_MODULE_KNOWLEDGE: str = ""
    STRIPE_PRICE_MODULE_LEVERAGE: str = ""
    STRIPE_PRICE_MODULE_REVERSE: str = ""
    STRIPE_PRICE_MODULE_OFFER: str = ""
    STRIPE_PRICE_MODULE_EXECUTION: str = ""

    # Security — TOTP encryption key (Fernet, 32-byte URL-safe base64)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # If empty, TOTP secrets are stored as plain base32 (dev-only acceptable)
    TOTP_ENCRYPTION_KEY_REF: str = ""
    TOTP_ENCRYPTION_KEY: str = ""

    # Resend email
    RESEND_API_KEY_REF: str = ""
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@nanovia.ca"
    RESEND_FROM_NAME: str = "Nanovia OS"
    TELEGRAM_BOT_TOKEN_REF: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    OPENAI_API_KEY_REF: str = ""
    OPENAI_API_KEY: str = ""
    OLLAMA_CLIENT_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_ADMIN_BASE_URL: str = "http://127.0.0.1:11435"
    OLLAMA_DEFAULT_MODEL: str = "llama3"

    ALLOWED_ORIGINS_RAW: str = "http://localhost:3000,http://localhost:3020"
    GRAFANA_ADMIN_PASSWORD: str = ""
    RATE_LIMIT_PER_MINUTE: int = Field(default=100, ge=1)

    # ── Computed properties ─────────────────────────────────────────────────────

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        origins = {
            origin.rstrip("/")
            for origin in [
                *self.ALLOWED_ORIGINS_RAW.split(","),
                self.PUBLIC_WEB_URL,
                self.PRIVATE_ADMIN_URL,
            ]
            if origin and origin.strip()
        }
        return sorted(origins)

    @property
    def ADMIN_ALLOWED_IPS(self) -> list[str]:
        return [
            cidr.strip()
            for cidr in self.ADMIN_ALLOWED_IPS_RAW.split(",")
            if cidr and cidr.strip()
        ]

    @property
    def PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS(self) -> list[str]:
        return [
            slug.strip()
            for slug in self.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW.split(",")
            if slug and slug.strip()
        ]

    @property
    def STRIPE_CHECKOUT_SUCCESS_URL(self) -> str:
        return f"{self.PUBLIC_WEB_URL}/dashboard?checkout=success"

    @property
    def STRIPE_CHECKOUT_CANCEL_URL(self) -> str:
        return f"{self.PUBLIC_WEB_URL}/#pricing"

    @property
    def STRIPE_PORTAL_RETURN_URL(self) -> str:
        return f"{self.PUBLIC_WEB_URL}/dashboard"

    @property
    def RESEND_FROM(self) -> str:
        return f"{self.RESEND_FROM_NAME} <{self.RESEND_FROM_EMAIL}>"

    # ── Validators ──────────────────────────────────────────────────────────────

    @model_validator(mode="before")
    @classmethod
    def resolve_managed_secrets(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        provider = str(data.get("SECRET_PROVIDER", "auto") or "auto").strip().lower()
        vault_addr = str(data.get("VAULT_ADDR", "http://127.0.0.1:8200") or "http://127.0.0.1:8200")
        vault_token = str(data.get("VAULT_TOKEN", "") or "")
        timeout_raw = data.get("VAULT_REQUEST_TIMEOUT_SECONDS", 5.0)
        try:
            timeout = float(timeout_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("VAULT_REQUEST_TIMEOUT_SECONDS must be a positive number") from exc
        if timeout <= 0:
            raise ValueError("VAULT_REQUEST_TIMEOUT_SECONDS must be greater than zero")

        for field_name, ref_name in (
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
            data[field_name] = resolve_secret_value(
                provider=provider,
                value=str(data.get(field_name, "") or ""),
                reference=str(data.get(ref_name, "") or ""),
                vault_addr=vault_addr,
                vault_token=vault_token,
                timeout=timeout,
            )
        return data

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL is required")
        allowed = ("postgresql+asyncpg://", "postgresql+psycopg://", "sqlite+aiosqlite://")
        if not any(v.startswith(p) for p in allowed):
            raise ValueError(
                "DATABASE_URL must start with postgresql+asyncpg://, "
                "postgresql+psycopg://, or sqlite+aiosqlite://"
            )
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        return v.upper()

    @field_validator(
        "API_BASE_URL",
        "PUBLIC_WEB_URL",
        "PRIVATE_ADMIN_URL",
        "PRIVATE_ORCHESTRATOR_UPSTREAM_URL",
        "OLLAMA_CLIENT_BASE_URL",
        "OLLAMA_ADMIN_BASE_URL",
        "VAULT_ADDR",
    )
    @classmethod
    def validate_http_urls(cls, v: str) -> str:
        value = v.strip()
        if not value:
            return ""
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return value.rstrip("/")

    @field_validator("PUBLIC_IP")
    @classmethod
    def validate_public_ip(cls, v: str) -> str:
        if not v or _looks_placeholder(v):
            return ""
        ipaddress.ip_address(v.strip())
        return v.strip()

    @field_validator("ADMIN_ALLOWED_IPS_RAW")
    @classmethod
    def validate_admin_allowed_ips(cls, v: str) -> str:
        if not v or _looks_placeholder(v):
            return ""
        items = [cidr.strip() for cidr in v.split(",") if cidr and cidr.strip()]
        for cidr in items:
            ipaddress.ip_network(cidr, strict=False)
        return ",".join(items)

    @field_validator("TOTP_ENCRYPTION_KEY")
    @classmethod
    def validate_totp_encryption_key(cls, v: str) -> str:
        if not v or _looks_placeholder(v):
            return ""
        from cryptography.fernet import Fernet

        try:
            Fernet(v.encode())
        except Exception as exc:  # noqa: BLE001
            raise ValueError("TOTP_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.APP_ENV == "production":
            errors = []
            if _looks_placeholder(self.JWT_SECRET_KEY):
                errors.append("JWT_SECRET_KEY cannot use placeholder values in production")
            if not self.STRIPE_SECRET_KEY.startswith("sk_live_"):
                errors.append("STRIPE_SECRET_KEY must be a live key (sk_live_...) in production")
            if not self.STRIPE_WEBHOOK_SECRET.startswith("whsec_"):
                errors.append("STRIPE_WEBHOOK_SECRET must start with whsec_")
            if not self.ADMIN_ALLOWED_IPS:
                errors.append("ADMIN_ALLOWED_IPS/ADMIN_ALLOWED_IP is required in production")
            if not self.TOTP_ENCRYPTION_KEY:
                errors.append("TOTP_ENCRYPTION_KEY is required in production")
            elif _looks_placeholder(self.TOTP_ENCRYPTION_KEY):
                errors.append("TOTP_ENCRYPTION_KEY cannot use placeholder values in production")
            origins = self.ALLOWED_ORIGINS
            if "*" in origins:
                errors.append("Wildcard CORS not allowed in production")
            if not self.API_BASE_URL.startswith("https://"):
                errors.append("API_BASE_URL must use https:// in production")
            if not self.PUBLIC_WEB_URL.startswith("https://"):
                errors.append("PUBLIC_WEB_URL must use https:// in production")
            if not self.PRIVATE_ADMIN_URL.startswith("https://"):
                errors.append("PRIVATE_ADMIN_URL must use https:// in production")
            for o in origins:
                if "localhost" in o or "127.0.0.1" in o:
                    errors.append(f"Dev origin {o!r} not allowed in production ALLOWED_ORIGINS_RAW")
            if errors:
                raise ValueError("Production config errors:\n" + "\n".join(f"  - {e}" for e in errors))
        return self

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
