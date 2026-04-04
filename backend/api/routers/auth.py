"""
backend/api/routers/auth.py — Register / Login / Refresh / Me / Password Reset
"""
from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.core.deps import CurrentUser, DB
from api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    needs_rehash,
)
from api.models.audit import AuditLog
from api.models.user import User
from api.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserPublic, ForgotPasswordRequest, ResetPasswordRequest, TwoFASetupResponse, TwoFAEnableRequest, TwoFADisableRequest, TwoFALoginRequest, LoginResponse
from api.services.email_service import send_welcome_email, send_password_reset_email

router = APIRouter()

_ACCESS_EXPIRE_SEC = settings.JWT_ACCESS_EXPIRE_MINUTES * 60


async def _audit(db: AsyncSession, action: str, user_id=None, ip=None, status="success", detail=None):
    db.add(AuditLog(
        user_id=user_id, action=action, ip_address=ip,
        status=status, detail=detail,
    ))


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, db: DB):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name or "",
    )
    db.add(user)
    await db.flush()
    await _audit(db, "register", user_id=user.id, ip=request.client.host if request.client else None)
    await db.commit()
    asyncio.create_task(send_welcome_email(user.email, user.full_name or user.email))
    return TokenResponse(
        access_token=create_access_token(str(user.id), extra={"plan": user.plan}),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=_ACCESS_EXPIRE_SEC,
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, db: DB):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    ip = request.client.host if request.client else None

    if not user or not verify_password(body.password, user.password_hash):
        await _audit(db, "login_failed", ip=ip, status="failed", detail=body.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    # Auto-upgrade bcrypt → Argon2id transparently
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        await db.commit()

    # ── 2FA gate ──────────────────────────────────────────────────────────
    if user.totp_enabled and user.totp_secret:
        # Issue a short-lived partial token — client must exchange with TOTP code
        from datetime import timedelta
        partial = _make_partial_token(str(user.id))
        await _audit(db, "login_2fa_required", user_id=user.id, ip=ip)
        await db.commit()
        return LoginResponse(requires_2fa=True, partial_token=partial, expires_in=300)

    await _audit(db, "login", user_id=user.id, ip=ip)
    await db.commit()
    return LoginResponse(
        access_token=create_access_token(str(user.id), extra={"plan": user.plan}),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=_ACCESS_EXPIRE_SEC,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: DB):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError
        user_id = payload["sub"]
    except (InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(str(user.id), extra={"plan": user.plan}),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=_ACCESS_EXPIRE_SEC,
    )


@router.get("/me", response_model=UserPublic)
async def me(current_user: CurrentUser):
    return UserPublic.model_validate(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: CurrentUser, db: DB):
    """
    Logout — invalidates device sessions for current user.
    Access token expires naturally (JWT stateless).
    Client MUST delete the refresh token from SecureStore/localStorage.
    """
    from sqlalchemy import update
    from api.models.device_session import DeviceSession
    # Deactivate all device sessions — forces re-auth on all devices
    # In practice, track specific device_id from request header for single-device logout
    await db.execute(
        update(DeviceSession)
        .where(DeviceSession.user_id == current_user.id)
        .values(is_active=False)
    )
    await db.commit()


_RESET_EXPIRE_HOURS = 1
_FRONTEND_URL = settings.PUBLIC_WEB_URL


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(body: ForgotPasswordRequest, db: DB):
    """
    Always returns 204 — never reveals if email exists (security best practice).
    Generates a secure token, saves it to DB, sends reset email via Resend.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=_RESET_EXPIRE_HOURS)
        await db.commit()
        reset_url = f"{_FRONTEND_URL}/reset-password?token={token}"
        asyncio.create_task(send_password_reset_email(user.email, reset_url))


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetPasswordRequest, db: DB):
    """
    Validates token, updates password, clears token.
    Returns 400 for invalid/expired token.
    """
    result = await db.execute(
        select(User).where(User.password_reset_token == body.token)
    )
    user = result.scalar_one_or_none()
    if not user or not user.password_reset_expires:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré")
    if user.password_reset_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Ce lien a expiré. Refais une demande.")
    user.password_hash = hash_password(body.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    await db.commit()
    await _audit(db, "password_reset", user_id=user.id)
    await db.commit()


# ─── 2FA helpers ──────────────────────────────────────────────────────────────

_2FA_PARTIAL_EXPIRE_SEC = 300  # 5 minutes


def _make_partial_token(user_id: str) -> str:
    """Short-lived token used only to complete the 2FA step."""
    from api.core.security import _make_token
    from datetime import timedelta
    return _make_token(user_id, expires_delta=timedelta(seconds=_2FA_PARTIAL_EXPIRE_SEC), extra={"type": "2fa_pending"})


def _verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code. Accepts ±1 time window for clock drift."""
    try:
        import pyotp
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
    except Exception:
        return False


# ─── 2FA Endpoints ────────────────────────────────────────────────────────────

@router.post("/2fa/setup", response_model=TwoFASetupResponse)
async def setup_2fa(current_user: CurrentUser, db: DB):
    """
    Initiate 2FA setup — generate a new TOTP secret.
    The secret is saved provisionally (totp_enabled remains False until verified).
    Client must display QR code and call /2fa/enable with a valid code.
    """
    import pyotp
    if current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA est déjà activé sur ce compte.")

    secret = pyotp.random_base32()
    current_user.totp_secret = secret
    db.add(current_user)
    await db.commit()

    totp = pyotp.TOTP(secret)
    issuer = "KT Monetization OS"
    uri = totp.provisioning_uri(name=current_user.email, issuer_name=issuer)

    return TwoFASetupResponse(provisioning_uri=uri, secret=secret)


@router.post("/2fa/enable", status_code=status.HTTP_204_NO_CONTENT)
async def enable_2fa(body: TwoFAEnableRequest, current_user: CurrentUser, db: DB):
    """
    Complete 2FA activation — verify the TOTP code from the authenticator app.
    Enables 2FA on the account. Subsequent logins will require TOTP.
    """
    if current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA est déjà activé.")
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Lance d'abord /2fa/setup pour obtenir un secret.")

    if not _verify_totp(current_user.totp_secret, body.totp_code):
        raise HTTPException(status_code=400, detail="Code invalide. Vérifie ton application et réessaie.")

    current_user.totp_enabled = True
    db.add(current_user)
    await _audit(db, "2fa_enabled", user_id=current_user.id)
    await db.commit()


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_2fa(body: TwoFADisableRequest, current_user: CurrentUser, db: DB):
    """
    Disable 2FA — requires either current TOTP code OR current password.
    Both are accepted to allow recovery if authenticator app is lost.
    """
    if not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA n'est pas activé.")

    # Accept TOTP code OR password as proof of identity
    verified = False
    if body.totp_code and current_user.totp_secret:
        verified = _verify_totp(current_user.totp_secret, body.totp_code)
    if not verified and body.password:
        verified = verify_password(body.password, current_user.password_hash)

    if not verified:
        raise HTTPException(
            status_code=403,
            detail="Code TOTP invalide ou mot de passe incorrect."
        )

    current_user.totp_enabled = False
    current_user.totp_secret = None
    db.add(current_user)
    await _audit(db, "2fa_disabled", user_id=current_user.id)
    await db.commit()


@router.post("/2fa/verify-login", response_model=TokenResponse)
async def verify_2fa_login(body: TwoFALoginRequest, request: Request, db: DB):
    """
    Exchange a 2FA partial token + TOTP code for a full JWT.
    Called after /login returns requires_2fa=True.
    """
    ip = request.client.host if request.client else None
    try:
        payload = decode_token(body.partial_token)
        if payload.get("type") != "2fa_pending":
            raise ValueError("wrong token type")
        user_id_str = payload["sub"]
    except (Exception,):
        raise HTTPException(status_code=401, detail="Token invalide ou expiré. Reconnecte-toi.")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id_str)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable.")
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA non activé sur ce compte.")

    if not _verify_totp(user.totp_secret, body.totp_code):
        await _audit(db, "2fa_login_failed", user_id=user.id, ip=ip, status="failed")
        await db.commit()
        raise HTTPException(status_code=401, detail="Code TOTP invalide.")

    await _audit(db, "login_2fa_verified", user_id=user.id, ip=ip)
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(str(user.id), extra={"plan": user.plan}),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=_ACCESS_EXPIRE_SEC,
    )
