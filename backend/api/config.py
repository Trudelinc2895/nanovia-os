"""backend/api/config.py — settings via env"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_NAME: str = "KT Monetization OS"
    APP_VERSION: str = "1.0.0"
    DOMAIN: str = "tkverse.ca"

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
    STRIPE_CREDIT_PRICE_ID: str = ""          # one-time payment price for credit packs
    STRIPE_CREDIT_PACK_SIZE: int = 100         # credits per pack
    STRIPE_CHECKOUT_SUCCESS_URL: str = "https://tkverse.ca/dashboard?checkout=success"
    STRIPE_CHECKOUT_CANCEL_URL: str = "https://tkverse.ca/#pricing"
    STRIPE_PORTAL_RETURN_URL: str = "https://tkverse.ca/dashboard"

    RESEND_API_KEY: str = ""

    OPENAI_API_KEY: str = ""
    OLLAMA_CLIENT_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_ADMIN_BASE_URL: str = "http://127.0.0.1:11435"
    OLLAMA_DEFAULT_MODEL: str = "llama3"

    ALLOWED_ORIGINS_RAW: str = "http://localhost:3000,http://localhost:3020"

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS_RAW.split(",")]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
