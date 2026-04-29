"""Helpers for protecting sensitive values at rest."""
from __future__ import annotations

import hashlib
import hmac

_HASH_PREFIX = "hmac-sha256:"
_ENCRYPTED_PREFIX = "enc::"


def hash_lookup_token(token: str) -> str:
    from api.config import settings

    digest = hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{_HASH_PREFIX}{digest}"


def lookup_token_matches(stored_value: str | None, candidate: str) -> bool:
    if not stored_value:
        return False
    if stored_value.startswith(_HASH_PREFIX):
        return hmac.compare_digest(stored_value, hash_lookup_token(candidate))
    return hmac.compare_digest(stored_value, candidate)


def protect_lookup_token(token: str) -> str:
    return hash_lookup_token(token)


def encrypt_at_rest(value: str) -> str:
    from api.config import settings

    if not settings.TOTP_ENCRYPTION_KEY:
        return value

    from cryptography.fernet import Fernet

    cipher = Fernet(settings.TOTP_ENCRYPTION_KEY.encode())
    encrypted = cipher.encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_ENCRYPTED_PREFIX}{encrypted}"


def decrypt_at_rest(value: str | None) -> str | None:
    from api.config import settings

    if value is None:
        return None
    if not value.startswith(_ENCRYPTED_PREFIX):
        return value
    if not settings.TOTP_ENCRYPTION_KEY:
        raise ValueError("TOTP_ENCRYPTION_KEY is required to decrypt protected values")

    from cryptography.fernet import Fernet

    cipher = Fernet(settings.TOTP_ENCRYPTION_KEY.encode())
    return cipher.decrypt(value[len(_ENCRYPTED_PREFIX) :].encode("utf-8")).decode("utf-8")
