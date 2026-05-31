"""backend/api/config.py — settings via env"""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.core.secret_manager import resolve_secret_value


_PLACEHOLDER_TOKENS = ("CHANGE_ME", "REPLACE_ME", "REPLACE_WITH", "GENERATE_WITH")
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
RUNTIME_RELOADABLE_FIELDS = (
    "LOG_LEVEL",
    "ADMIN_ALLOWED_IPS_RAW",
    "PRIVATE_ORCHESTRATOR_ENABLED",
    "NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED",
    "PRIVATE_ORCHESTRATOR_UPSTREAM_URL",
    "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW",
    "OLLAMA_CLIENT_BASE_URL",
    "OLLAMA_ADMIN_BASE_URL",
    "OLLAMA_DEFAULT_MODEL",
)
RUNTIME_NON_RELOADABLE_AREAS = (
    "DATABASE_*",
    "REDIS_*",
    "JWT_*",
    "STRIPE_*",
    "POSTGRES_*",
    "TOTP_*",
    "RESEND_*",
    "OPENAI_*",
    "TELEGRAM_BOT_TOKEN",
    "SCRAPING_*",
)


def _looks_placeholder(value: str) -> bool:
    upper = value.strip().upper()
    return not upper or any(token in upper for token in _PLACEHOLDER_TOKENS)


class Settings(BaseSettings):
    APP_ENV: Literal["development", "staging", "production", "test", "sandbox"] = "development"
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
    STRIPE_MODE: Literal["test", "live"] = "test"
    STRIPE_SECRET_KEY_REF: str = ""
    STRIPE_WEBHOOK_SECRET_REF: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    TURNSTILE_SITE_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("TURNSTILE_SITE_KEY", "NEXT_PUBLIC_TURNSTILE_SITE_KEY"),
    )
    TURNSTILE_SECRET_KEY_REF: str = ""
    TURNSTILE_SECRET_KEY: str = ""
    TURNSTILE_ENABLED: bool = False
    TURNSTILE_PROTECT_LOGIN: bool = True
    TURNSTILE_PROTECT_REGISTER: bool = True
    TURNSTILE_PROTECT_CONTACT: bool = True
    TURNSTILE_PROTECT_BILLING: bool = True
    TURNSTILE_SITEVERIFY_URL: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    TURNSTILE_ALLOWED_HOSTNAMES_RAW: str = ""
    AGENTS_ENABLED: bool = True
    ORCHESTRATOR_ENABLED: bool = True
    MEMORY_ENABLED: bool = True
    BOTS_ENABLED: bool = True
    DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION: bool = True
    SANDBOX_ALLOW_LIVE_KEYS: bool = False
    AUDIT_LOG_ENABLED: bool = True
    STRIPE_PRICE_STARTER_MONTHLY_ID: str = ""
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
    AI_MODEL: str = "gpt-4.1-mini"
    AI_STATE_DIR: str = ""
    AI_ADMIN_API_KEY: str = ""
    OPENAI_COST_GUARD_ENABLED: bool = True
    OPENAI_MAX_MONTHLY_COST_USD: float = Field(default=45.0, ge=0)
    OPENAI_TARGET_GROSS_MARGIN_PCT: int = Field(default=70, ge=0, le=100)
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    CORTEX_SUMMARY_MODEL: str = "gpt-4o-mini"
    CORTEX_ENABLED: bool = False
    CORTEX_TOP_K: int = Field(default=3, ge=1, le=10)
    CORTEX_MAX_SUMMARY_ITEMS: int = Field(default=5, ge=1, le=20)
    CORTEX_EMBEDDING_DIMENSIONS: int = Field(default=1536, ge=1)
    CORTEX_AUTO_SUMMARY_INTERVAL: int = Field(default=50, ge=1)
    CORTEX_FREE_MAX_MEMORIES_PER_USER: int = Field(default=25, ge=1)
    OLLAMA_CLIENT_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_ADMIN_BASE_URL: str = "http://127.0.0.1:11435"
    OLLAMA_DEFAULT_MODEL: str = "llama3"

    ALLOWED_ORIGINS_RAW: str = "http://localhost:3000,http://localhost:3020"
    GRAFANA_ADMIN_PASSWORD: str = ""
    RATE_LIMIT_PER_MINUTE: int = Field(default=100, ge=1)

    # Scraping (secure proxy layer)
    SCRAPING_ENABLED: bool = Field(
        default=False,
        validation_alias=AliasChoices("SCRAPING_ENABLED"),
    )
    SCRAPING_PROXY_LAYER_ENABLED: bool = Field(
        default=False,
        validation_alias=AliasChoices("SCRAPING_PROXY_LAYER_ENABLED", "ENABLE_SCRAPE_PROXY"),
    )
    SCRAPING_ALLOWLIST_RAW: str = Field(
        default="",
        validation_alias=AliasChoices("SCRAPING_ALLOWLIST_RAW", "SCRAPE_ALLOWED_DOMAINS"),
    )
    SCRAPING_STRICT_ALLOWLIST: bool = True
    SCRAPING_REQUIRE_AUTH: bool = Field(
        default=False,
        validation_alias=AliasChoices("SCRAPING_REQUIRE_AUTH", "SCRAPE_REQUIRE_AUTH"),
    )
    SCRAPING_MODE_DEFAULT: Literal["sync", "async"] = Field(
        default="sync",
        validation_alias=AliasChoices("SCRAPING_MODE_DEFAULT", "SCRAPE_MODE"),
    )
    SCRAPING_BLOCK_PRIVATE_IPS: bool = Field(
        default=True,
        validation_alias=AliasChoices("SCRAPING_BLOCK_PRIVATE_IPS", "SCRAPE_BLOCK_PRIVATE_IPS"),
    )
    SCRAPING_CACHE_TTL_SECONDS: int = Field(
        default=900,
        ge=1,
        validation_alias=AliasChoices("SCRAPING_CACHE_TTL_SECONDS", "SCRAPE_TTL_SECONDS", "SCRAPE_CACHE_TTL_SECONDS"),
    )
    SCRAPING_CACHE_STALE_TTL_SECONDS: int = Field(
        default=3600,
        ge=1,
        validation_alias=AliasChoices("SCRAPING_CACHE_STALE_TTL_SECONDS", "SCRAPE_CACHE_STALE_TTL_SECONDS"),
    )
    SCRAPING_MAX_RESPONSE_BYTES: int = Field(
        default=2_000_000,
        ge=1024,
        validation_alias=AliasChoices("SCRAPING_MAX_RESPONSE_BYTES", "SCRAPE_MAX_RESPONSE_BYTES"),
    )
    SCRAPING_MAX_REDIRECTS: int = Field(
        default=3,
        ge=0,
        le=10,
        validation_alias=AliasChoices("SCRAPING_MAX_REDIRECTS", "SCRAPE_MAX_REDIRECTS"),
    )
    SCRAPING_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0.1, le=120.0)
    SCRAPING_RATE_LIMIT_PER_DOMAIN_PER_MIN: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices(
            "SCRAPING_RATE_LIMIT_PER_DOMAIN_PER_MIN",
            "RATE_LIMIT_MAX_PER_DOMAIN",
            "SCRAPE_RATE_LIMIT_DOMAIN_PER_MINUTE",
        ),
    )
    SCRAPING_RATE_LIMIT_CLIENT_PER_MIN: int = Field(
        default=60,
        ge=0,
        validation_alias=AliasChoices("SCRAPING_RATE_LIMIT_CLIENT_PER_MIN", "SCRAPE_RATE_LIMIT_CLIENT_PER_MINUTE"),
    )
    SCRAPING_RETRY_MAX_ATTEMPTS: int = Field(
        default=3,
        ge=1,
        le=8,
        validation_alias=AliasChoices("SCRAPING_RETRY_MAX_ATTEMPTS", "SCRAPE_MAX_RETRIES", "SCRAPE_RETRY_ATTEMPTS"),
    )
    SCRAPING_RETRY_BACKOFF_BASE_MS: int = Field(
        default=250,
        ge=50,
        le=10_000,
        validation_alias=AliasChoices("SCRAPING_RETRY_BACKOFF_BASE_MS", "SCRAPE_RETRY_BACKOFF_MS"),
    )
    SCRAPING_CIRCUIT_FAIL_THRESHOLD: int = Field(
        default=5,
        ge=1,
        le=100,
        validation_alias=AliasChoices("SCRAPING_CIRCUIT_FAIL_THRESHOLD", "SCRAPE_CIRCUIT_FAILURE_THRESHOLD"),
    )
    SCRAPING_CIRCUIT_OPEN_SECONDS: int = Field(default=60, ge=5, le=3600)
    SCRAPING_PROXY_ROTATION_ENABLED: bool = Field(
        default=False,
        validation_alias=AliasChoices("SCRAPING_PROXY_ROTATION_ENABLED", "SCRAPE_PROXY_ENABLED"),
    )
    SCRAPING_PROXY_LIST_RAW: str = Field(
        default="",
        validation_alias=AliasChoices("SCRAPING_PROXY_LIST_RAW", "SCRAPE_PROXY_URLS"),
    )
    SCRAPING_PROXY_BYPASS_DOMAINS_RAW: str = ""
    SCRAPING_RUN_WORKER_IN_API: bool = False
    SCRAPING_JITTER_MIN_MS: int = Field(default=25, ge=0, le=2000)
    SCRAPING_JITTER_MAX_MS: int = Field(default=120, ge=0, le=5000)
    SCRAPING_BROWSER_POOL_SIZE: int = Field(default=2, ge=1, le=20)
    SCRAPING_QUEUE_MAX_DEPTH: int = Field(
        default=1000,
        ge=1,
        validation_alias=AliasChoices("SCRAPING_QUEUE_MAX_DEPTH", "SCRAPE_QUEUE_MAX_WAITING"),
    )
    SCRAPING_QUEUE_CONCURRENCY: int = Field(
        default=3,
        ge=1,
        le=32,
        validation_alias=AliasChoices("SCRAPING_QUEUE_CONCURRENCY", "SCRAPE_QUEUE_CONCURRENCY"),
    )
    SCRAPING_QUEUE_JOB_TIMEOUT_MS: int = Field(
        default=30_000,
        ge=1_000,
        le=300_000,
        validation_alias=AliasChoices("SCRAPING_QUEUE_JOB_TIMEOUT_MS", "SCRAPE_QUEUE_JOB_TIMEOUT_MS"),
    )
    SCRAPING_DEDUPE_TTL_SECONDS: int = Field(default=300, ge=1)
    SCRAPING_JOB_TTL_SECONDS: int = Field(default=3600, ge=60)
    SCRAPING_CLIENT_DAILY_QUOTA: int = Field(default=0, ge=0)
    SCRAPING_CLIENT_MAX_QUEUED_JOBS: int = Field(default=0, ge=0)
    SCRAPING_ALLOWED_CONTENT_TYPES_RAW: str = Field(
        default="text/html,text/plain,application/json,application/xml,text/xml",
        validation_alias=AliasChoices("SCRAPING_ALLOWED_CONTENT_TYPES_RAW", "SCRAPE_ALLOWED_CONTENT_TYPES"),
    )
    SCRAPING_USER_AGENT: str = Field(
        default="nanovia-scraper/1.0",
        validation_alias=AliasChoices("SCRAPING_USER_AGENT", "SCRAPE_USER_AGENT"),
    )
    SCRAPING_ACCEPT_LANGUAGE: str = Field(
        default="fr-CA,fr;q=0.9,en;q=0.8",
        validation_alias=AliasChoices("SCRAPING_ACCEPT_LANGUAGE", "SCRAPE_ACCEPT_LANGUAGE"),
    )
    SCRAPING_FEATURE_PROXY_ENABLED: bool = Field(
        default=True,
        validation_alias=AliasChoices("SCRAPING_FEATURE_PROXY_ENABLED", "SCRAPE_PROXY_ENABLED"),
    )
    SCRAPING_FEATURE_BROWSER_ENABLED: bool = True
    SCRAPING_FEATURE_ASYNC_QUEUE_ENABLED: bool = True
    SCRAPING_FEATURE_CACHE_FALLBACK_ENABLED: bool = True
    SCRAPING_FALLBACK_DIRECT_ENABLED: bool = Field(
        default=True,
        validation_alias=AliasChoices("SCRAPING_FALLBACK_DIRECT_ENABLED", "SCRAPE_FALLBACK_DIRECT_ENABLED"),
    )
    SCRAPING_REDIS_REQUIRED: bool = Field(
        default=False,
        validation_alias=AliasChoices("SCRAPING_REDIS_REQUIRED", "SCRAPE_REDIS_REQUIRED"),
    )
    SCRAPING_METRICS_ENABLED: bool = Field(
        default=True,
        validation_alias=AliasChoices("SCRAPING_METRICS_ENABLED", "SCRAPE_METRICS_ENABLED"),
    )

    # Stealth scraping (all off by default — zero behaviour change for existing deployments)
    SCRAPING_STEALTH_MODE: bool = False
    SCRAPING_STEALTH_SCROLL_SIMULATE: bool = True
    SCRAPING_STEALTH_HEADER_ROTATION: bool = True
    SCRAPING_STEALTH_PROFILE: str = "chrome-windows"
    SCRAPING_STEALTH_TIMEZONE: str = Field(
        default="UTC",
        validation_alias=AliasChoices("SCRAPING_STEALTH_TIMEZONE", "SCRAPE_TIMEZONE"),
    )
    SCRAPING_STEALTH_VIEWPORT_WIDTH: int = Field(
        default=1366,
        ge=800,
        le=3840,
        validation_alias=AliasChoices("SCRAPING_STEALTH_VIEWPORT_WIDTH", "SCRAPE_VIEWPORT_WIDTH"),
    )
    SCRAPING_STEALTH_VIEWPORT_HEIGHT: int = Field(
        default=768,
        ge=600,
        le=2160,
        validation_alias=AliasChoices("SCRAPING_STEALTH_VIEWPORT_HEIGHT", "SCRAPE_VIEWPORT_HEIGHT"),
    )
    SCRAPING_PROXY_HEALTH_CHECK_INTERVAL_SECONDS: int = 300
    SCRAPING_PROXY_HEALTH_CHECK_URL: str = "https://httpbin.org/ip"
    SCRAPING_WORKER_HEARTBEAT_INTERVAL_SECONDS: int = Field(default=10, ge=1, le=300)
    SCRAPING_WORKER_HEARTBEAT_TTL_SECONDS: int = Field(default=30, ge=5, le=900)

    # URL risk scoring
    SCRAPING_RISK_SCORE_THRESHOLD: float = 0.75
    SCRAPING_RISK_SCORING_ENABLED: bool = False

    # Governance — per-API-key budgets (0 = disabled)
    SCRAPING_API_KEY_HOURLY_BUDGET: int = Field(default=0, ge=0)
    SCRAPING_API_KEY_DAILY_BUDGET: int = Field(default=0, ge=0)
    SCRAPING_ANOMALY_DETECTION_ENABLED: bool = False
    SCRAPING_ANOMALY_BASELINE_MULTIPLIER: float = Field(default=3.0, gt=1.0)

    # Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    APP_REGION: str = "local"

    # Slowloris / large-body protection
    API_REQUEST_TIMEOUT_SECONDS: float = 30.0
    API_BODY_SIZE_LIMIT_BYTES: int = 1_048_576  # 1 MB

    # Chaos engineering (MUST be disabled in production)
    CHAOS_ENABLED: bool = False

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
    def TURNSTILE_ALLOWED_HOSTNAMES(self) -> list[str]:
        hostnames = {
            hostname.strip().lower()
            for hostname in self.TURNSTILE_ALLOWED_HOSTNAMES_RAW.split(",")
            if hostname and hostname.strip()
        }
        for candidate in (self.DOMAIN, self.PUBLIC_WEB_URL, self.PRIVATE_ADMIN_URL):
            if not candidate:
                continue
            if candidate.startswith(("http://", "https://")):
                parsed = urlparse(candidate)
                if parsed.hostname:
                    hostnames.add(parsed.hostname.lower())
                continue
            hostnames.add(candidate.strip().lower())
        return sorted(hostnames)

    @property
    def RESEND_FROM(self) -> str:
        return f"{self.RESEND_FROM_NAME} <{self.RESEND_FROM_EMAIL}>"

    @property
    def SCRAPING_ALLOWLIST(self) -> list[str]:
        return sorted({
            domain.strip().lower()
            for domain in self.SCRAPING_ALLOWLIST_RAW.split(",")
            if domain and domain.strip()
        })

    @property
    def SCRAPING_PROXY_LIST(self) -> list[str]:
        return [
            proxy.strip()
            for proxy in self.SCRAPING_PROXY_LIST_RAW.split(",")
            if proxy and proxy.strip()
        ]

    @property
    def SCRAPING_PROXY_BYPASS_DOMAINS(self) -> list[str]:
        return sorted({
            domain.strip().lower().lstrip(".")
            for domain in self.SCRAPING_PROXY_BYPASS_DOMAINS_RAW.split(",")
            if domain and domain.strip()
        })

    @property
    def SCRAPING_ALLOWED_CONTENT_TYPES(self) -> list[str]:
        return [
            content_type.strip().lower()
            for content_type in self.SCRAPING_ALLOWED_CONTENT_TYPES_RAW.split(",")
            if content_type and content_type.strip()
        ]

    # ── Validators ──────────────────────────────────────────────────────────────

    @model_validator(mode="before")
    @classmethod
    def resolve_managed_secrets(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        scrape_timeout_ms = data.get("SCRAPE_TIMEOUT_MS")
        if scrape_timeout_ms is None:
            scrape_timeout_ms = os.getenv("SCRAPE_TIMEOUT_MS")
        if "SCRAPING_TIMEOUT_SECONDS" not in data and scrape_timeout_ms is not None:
            try:
                data["SCRAPING_TIMEOUT_SECONDS"] = float(scrape_timeout_ms) / 1000.0
            except (TypeError, ValueError) as exc:
                raise ValueError("SCRAPE_TIMEOUT_MS must be a positive integer") from exc

        scrape_circuit_reset_ms = data.get("SCRAPE_CIRCUIT_RESET_TIMEOUT_MS")
        if scrape_circuit_reset_ms is None:
            scrape_circuit_reset_ms = os.getenv("SCRAPE_CIRCUIT_RESET_TIMEOUT_MS")
        if "SCRAPING_CIRCUIT_OPEN_SECONDS" not in data and scrape_circuit_reset_ms is not None:
            try:
                data["SCRAPING_CIRCUIT_OPEN_SECONDS"] = max(1, int(scrape_circuit_reset_ms) // 1000)
            except (TypeError, ValueError) as exc:
                raise ValueError("SCRAPE_CIRCUIT_RESET_TIMEOUT_MS must be a positive integer") from exc

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
            ("TURNSTILE_SECRET_KEY", "TURNSTILE_SECRET_KEY_REF"),
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
    def validate_scraping_limits(self) -> "Settings":
        if self.SCRAPING_JITTER_MAX_MS < self.SCRAPING_JITTER_MIN_MS:
            raise ValueError("SCRAPING_JITTER_MAX_MS must be >= SCRAPING_JITTER_MIN_MS")
        if self.SCRAPING_PROXY_ROTATION_ENABLED and not self.SCRAPING_PROXY_LIST:
            raise ValueError("SCRAPING_PROXY_ROTATION_ENABLED=true requires SCRAPING_PROXY_LIST_RAW")
        if self.SCRAPING_TIMEOUT_SECONDS <= 0:
            raise ValueError("SCRAPING_TIMEOUT_SECONDS must be > 0")
        if self.SCRAPING_CACHE_STALE_TTL_SECONDS < self.SCRAPING_CACHE_TTL_SECONDS:
            raise ValueError("SCRAPING_CACHE_STALE_TTL_SECONDS must be >= SCRAPING_CACHE_TTL_SECONDS")
        if self.SCRAPING_QUEUE_JOB_TIMEOUT_MS < int(self.SCRAPING_TIMEOUT_SECONDS * 1000):
            raise ValueError("SCRAPING_QUEUE_JOB_TIMEOUT_MS must be >= SCRAPING_TIMEOUT_SECONDS")
        return self

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.APP_ENV == "production":
            errors = []
            stripe_live_secret_prefix = "sk" + "_live_"
            stripe_webhook_prefix = "wh" + "sec_"
            if _looks_placeholder(self.JWT_SECRET_KEY):
                errors.append("JWT_SECRET_KEY cannot use placeholder values in production")
            if not self.STRIPE_SECRET_KEY.startswith(stripe_live_secret_prefix):
                errors.append("STRIPE_SECRET_KEY must be a live Stripe key in production")
            if not self.STRIPE_WEBHOOK_SECRET.startswith(stripe_webhook_prefix):
                errors.append("STRIPE_WEBHOOK_SECRET must be a Stripe webhook signing secret")
            if not self.ADMIN_ALLOWED_IPS:
                errors.append("ADMIN_ALLOWED_IPS/ADMIN_ALLOWED_IP is required in production")
            if not self.TOTP_ENCRYPTION_KEY:
                errors.append("TOTP_ENCRYPTION_KEY is required in production")
            elif _looks_placeholder(self.TOTP_ENCRYPTION_KEY):
                errors.append("TOTP_ENCRYPTION_KEY cannot use placeholder values in production")
            if self.TURNSTILE_ENABLED:
                if not self.TURNSTILE_SITE_KEY:
                    errors.append("TURNSTILE_SITE_KEY/NEXT_PUBLIC_TURNSTILE_SITE_KEY is required when TURNSTILE_ENABLED=true")
                if not self.TURNSTILE_SECRET_KEY:
                    errors.append("TURNSTILE_SECRET_KEY is required when TURNSTILE_ENABLED=true")
                elif _looks_placeholder(self.TURNSTILE_SECRET_KEY):
                    errors.append("TURNSTILE_SECRET_KEY cannot use placeholder values in production")
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

    @model_validator(mode="after")
    def validate_sandbox_secrets(self) -> "Settings":
        if self.APP_ENV != "sandbox":
            return self

        if self.STRIPE_MODE != "test":
            raise ValueError("STRIPE_MODE must be 'test' in sandbox")

        live_key_prefixes = ("sk_live_", "pk_live_")
        if (
            not self.SANDBOX_ALLOW_LIVE_KEYS
            and (
                self.STRIPE_SECRET_KEY.startswith(live_key_prefixes)
                or self.STRIPE_PUBLIC_KEY.startswith(live_key_prefixes)
            )
        ):
            raise ValueError("Live Stripe keys are forbidden when SANDBOX_ALLOW_LIVE_KEYS=false")

        if (
            not self.SANDBOX_ALLOW_LIVE_KEYS
            and self.STRIPE_WEBHOOK_SECRET
            and self.STRIPE_WEBHOOK_SECRET.lower().startswith("whsec_live")
        ):
            raise ValueError("Live Stripe webhook secrets are forbidden when SANDBOX_ALLOW_LIVE_KEYS=false")

        return self

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()


def get_runtime_settings_snapshot() -> dict[str, object]:
    snapshot = {field: getattr(settings, field) for field in RUNTIME_RELOADABLE_FIELDS}
    snapshot["ADMIN_ALLOWED_IPS"] = settings.ADMIN_ALLOWED_IPS
    snapshot["PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS"] = settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS
    return snapshot


def reload_runtime_settings(*, dry_run: bool = False) -> dict[str, object]:
    fresh_settings = Settings()
    changed: dict[str, dict[str, object]] = {}

    for field in RUNTIME_RELOADABLE_FIELDS:
        current_value = getattr(settings, field)
        new_value = getattr(fresh_settings, field)
        if current_value == new_value:
            continue
        changed[field] = {"old": current_value, "new": new_value}
        if not dry_run:
            setattr(settings, field, new_value)

    if not dry_run and "LOG_LEVEL" in changed:
        from api.core.logging import setup_logging

        setup_logging(level=settings.LOG_LEVEL)

    applied_snapshot = get_runtime_settings_snapshot() if not dry_run else {
        **{field: change["new"] for field, change in changed.items()},
        **{
            field: getattr(settings, field)
            for field in RUNTIME_RELOADABLE_FIELDS
            if field not in changed
        },
        "ADMIN_ALLOWED_IPS": fresh_settings.ADMIN_ALLOWED_IPS,
        "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS": fresh_settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS,
    }

    return {
        "dry_run": dry_run,
        "changed": changed,
        "applied": applied_snapshot,
        "reloadable_fields": list(RUNTIME_RELOADABLE_FIELDS),
        "non_reloadable_areas": list(RUNTIME_NON_RELOADABLE_AREAS),
    }
