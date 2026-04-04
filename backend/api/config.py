"""backend/api/config.py — settings via env"""
from __future__ import annotations

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_NAME: str = "KT Monetization OS"
    APP_VERSION: str = "1.0.0"
    DOMAIN: str = "tkverse.ca"
    LOG_LEVEL: str = "INFO"

    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8010
    API_BASE_URL: str = "http://127.0.0.1:8010"
    PUBLIC_WEB_URL: str = "http://127.0.0.1:3000"
    PRIVATE_ADMIN_URL: str = "http://127.0.0.1:3020"

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    VAULT_ADDR: str = "http://127.0.0.1:8200"

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_EXPIRE_DAYS: int = 30
    JWT_ISSUER: str = "tkverse"
    JWT_AUDIENCE: str = "tkverse-users"

    STRIPE_PUBLIC_KEY: str = ""
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
    TOTP_ENCRYPTION_KEY: str = ""

    # Resend email
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@tkverse.ca"
    RESEND_FROM_NAME: str = "KT Monetization OS"

    OPENAI_API_KEY: str = ""
    OLLAMA_CLIENT_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_ADMIN_BASE_URL: str = "http://127.0.0.1:11435"
    OLLAMA_DEFAULT_MODEL: str = "llama3"

    ALLOWED_ORIGINS_RAW: str = "http://localhost:3000,http://localhost:3020"

    # ── Computed properties ─────────────────────────────────────────────────────

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS_RAW.split(",") if o.strip()]

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
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return upper

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.APP_ENV == "production":
            errors = []
            if not self.STRIPE_SECRET_KEY.startswith("sk_live_"):
                errors.append("STRIPE_SECRET_KEY must be a live key (sk_live_...) in production")
            if not self.STRIPE_WEBHOOK_SECRET.startswith("whsec_"):
                errors.append("STRIPE_WEBHOOK_SECRET must start with whsec_")
            origins = self.ALLOWED_ORIGINS
            if "*" in origins:
                errors.append("Wildcard CORS not allowed in production")
            for o in origins:
                if "localhost" in o or "127.0.0.1" in o:
                    errors.append(f"Dev origin {o!r} not allowed in production ALLOWED_ORIGINS_RAW")
            if errors:
                raise ValueError("Production config errors:\n" + "\n".join(f"  - {e}" for e in errors))
        return self

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
