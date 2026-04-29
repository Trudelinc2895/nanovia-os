"""Unit tests for encryption and token protection helpers."""

from __future__ import annotations

from cryptography.fernet import Fernet

from api.core.data_protection import (
    decrypt_at_rest,
    encrypt_at_rest,
    lookup_token_matches,
    protect_lookup_token,
)


def test_lookup_token_matches_hashed_and_legacy_values(monkeypatch):
    from api.config import settings

    previous_key = settings.JWT_SECRET_KEY
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "x" * 40)

    try:
        protected = protect_lookup_token("token-123")

        assert protected != "token-123"
        assert lookup_token_matches(protected, "token-123") is True
        assert lookup_token_matches("legacy-token", "legacy-token") is True
        assert lookup_token_matches(protected, "wrong-token") is False
    finally:
        settings.JWT_SECRET_KEY = previous_key


def test_encrypt_at_rest_roundtrip(monkeypatch):
    from api.config import settings

    previous_key = settings.TOTP_ENCRYPTION_KEY
    monkeypatch.setattr(settings, "TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())

    try:
        stored = encrypt_at_rest("push-token-secret")

        assert stored != "push-token-secret"
        assert stored.startswith("enc::")
        assert decrypt_at_rest(stored) == "push-token-secret"
    finally:
        settings.TOTP_ENCRYPTION_KEY = previous_key
