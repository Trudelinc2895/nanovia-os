"""Deterministic environment shared by every backend test module.

These values must be assigned before test collection imports ``api.settings``.
Using ``setdefault`` leaks host or staging values into the process and makes the
suite depend on module collection order.
"""

import os


os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_auth.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-auth-tests"
os.environ["APP_ENV"] = "test"
os.environ["ALLOWED_ORIGINS_RAW"] = "http://localhost:3000"
os.environ["PUBLIC_WEB_URL"] = "http://localhost:3000"
os.environ["PRIVATE_ADMIN_URL"] = "http://localhost:3020"
os.environ["API_BASE_URL"] = "http://127.0.0.1:8010"
# Closed loopback port: fail immediately and deterministically without network.
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"

# Tests must never inherit credentials or trigger outbound provider calls from
# the developer shell or a local runtime env file.
for key in (
    "RESEND_API_KEY",
    "RESEND_API_KEY_REF",
    "OPENAI_API_KEY",
    "OPENAI_API_KEY_REF",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN_REF",
    "TELEGRAM_CHAT_ID",
    "STRIPE_SECRET_KEY",
    "STRIPE_SECRET_KEY_REF",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_WEBHOOK_SECRET_REF",
):
    os.environ[key] = ""
