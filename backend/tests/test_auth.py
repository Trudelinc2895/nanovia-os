"""
Unit tests for authentication utilities — JWT security, PII filter, structured logging.
"""
from __future__ import annotations

import logging
import pytest


# ── core/security.py ──────────────────────────────────────────────────────────

def test_create_access_token_contains_expected_claims():
    """create_access_token should embed sub, type=access, and expiry."""
    from api.core.security import create_access_token
    token = create_access_token(user_id="user-123")
    import jwt as _jwt
    from api.config import settings
    payload = _jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        options={"verify_exp": False},
    )
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_create_refresh_token_type_is_refresh():
    """create_refresh_token should produce a token with type=refresh."""
    from api.core.security import create_refresh_token
    token = create_refresh_token(user_id="user-456")
    import jwt as _jwt
    from api.config import settings
    payload = _jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        options={"verify_exp": False},
    )
    assert payload["type"] == "refresh"


def test_decode_token_returns_payload():
    """decode_token should return the correct payload for a valid token."""
    from api.core.security import create_access_token, decode_token
    token = create_access_token(user_id="abc-def")
    payload = decode_token(token)
    assert payload["sub"] == "abc-def"


def test_decode_token_rejects_tampered_token():
    """decode_token should raise on a tampered token."""
    from api.core.security import create_access_token, decode_token
    import jwt.exceptions
    token = create_access_token(user_id="tamper-me") + "x"
    with pytest.raises(jwt.exceptions.InvalidTokenError):
        decode_token(token)


def test_hash_password_is_not_plaintext():
    """hash_password should return an Argon2id hash, not the original password."""
    from api.core.security import hash_password
    hashed = hash_password("mysecretpassword")
    assert hashed != "mysecretpassword"
    assert "$argon2" in hashed or hashed.startswith("$2")


def test_verify_password_correct():
    """verify_password should return True for a matching pair."""
    from api.core.security import hash_password, verify_password
    pw = "correct-horse-battery"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed) is True


def test_verify_password_wrong():
    """verify_password should return False for a wrong password."""
    from api.core.security import hash_password, verify_password
    hashed = hash_password("correct-pass")
    assert verify_password("wrong-pass", hashed) is False


# ── middleware/pii.py ──────────────────────────────────────────────────────────

def test_pii_filter_masks_email():
    """PIIFilter should mask email addresses in log messages."""
    from api.middleware.pii import PIIFilter
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="user email is alice@example.com logged in", args=(), exc_info=None,
    )
    f = PIIFilter()
    f.filter(record)
    assert "alice@example.com" not in record.msg
    assert "***" in record.msg


def test_pii_filter_masks_ip():
    """PIIFilter should mask the last octet of IPv4 addresses."""
    from api.middleware.pii import PIIFilter
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="request from 192.168.1.100", args=(), exc_info=None,
    )
    f = PIIFilter()
    f.filter(record)
    assert "192.168.1.100" not in record.msg
    assert "***" in record.msg


def test_pii_filter_masks_jwt():
    """PIIFilter should redact JWT bearer tokens."""
    from api.middleware.pii import PIIFilter
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="auth: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
        args=(), exc_info=None,
    )
    f = PIIFilter()
    f.filter(record)
    assert "[REDACTED]" in record.msg


# ── core/logging.py ───────────────────────────────────────────────────────────

def test_structured_formatter_emits_json():
    """StructuredFormatter should produce valid JSON with required fields."""
    import json
    from api.core.logging import StructuredFormatter
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test.logger", level=logging.INFO, pathname="", lineno=0,
        msg="hello world", args=(), exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["service"] == "api"
    assert "ts" in parsed
    assert "traceId" in parsed
    assert "region" in parsed


def test_structured_formatter_merges_dict_msg():
    """StructuredFormatter should merge dict messages into the top-level JSON."""
    import json
    from api.core.logging import StructuredFormatter
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test.logger", level=logging.INFO, pathname="", lineno=0,
        msg={"event": "scrape_completed", "url": "https://example.com"},
        args=(), exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["event"] == "scrape_completed"
    assert parsed["url"] == "https://example.com"
