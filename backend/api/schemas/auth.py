"""
backend/api/schemas/auth.py — Auth request/response schemas
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)
    turnstile_token: str | None = Field(default=None, max_length=2048)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Le mot de passe doit contenir au moins une majuscule")
        if not any(c.isdigit() for c in v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    turnstile_token: str | None = Field(default=None, max_length=2048)


class RefreshRequest(BaseModel):
    refresh_token: str | None = None  # Optional — server reads from httpOnly cookie if not provided


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Le mot de passe doit contenir au moins une majuscule")
        if not any(c.isdigit() for c in v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    plan: str
    is_verified: bool
    is_admin: bool = False
    credits: int = 0
    totp_enabled: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 2FA Schemas ───────────────────────────────────────────────────────────────

class TwoFASetupResponse(BaseModel):
    """Returned when user initiates 2FA setup. Show QR + secret ONCE."""
    provisioning_uri: str    # otpauth:// URI for QR code apps (Authenticator, Authy)
    secret: str              # Base32 secret — displayed once for manual entry / backup
    qr_code_base64: str | None = None  # Server-generated QR PNG (base64) — avoids leaking URI to Google


class TwoFAEnableRequest(BaseModel):
    totp_code: str = Field(..., min_length=6, max_length=6, pattern="^[0-9]{6}$")


class TwoFADisableRequest(BaseModel):
    totp_code: str | None = Field(None, min_length=6, max_length=6, pattern="^[0-9]{6}$")
    password: str | None = None  # Accepted as alternative proof of identity


class TwoFALoginRequest(BaseModel):
    partial_token: str
    totp_code: str = Field(..., min_length=6, max_length=6, pattern="^[0-9]{6}$")


class LoginResponse(BaseModel):
    """
    Unified login response — covers both standard auth and 2FA challenge.

    Standard auth: access_token + refresh_token present, requires_2fa=False.
    2FA required:  partial_token present, access_token=None, requires_2fa=True.
    """
    # Standard auth fields
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    # 2FA challenge fields
    requires_2fa: bool = False
    partial_token: str | None = None
