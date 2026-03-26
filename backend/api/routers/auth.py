"""
backend/api/routers/auth.py — Register / Login / Refresh / Me
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.core.deps import CurrentUser, DB, get_db
from api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from api.database import get_db
from api.models.audit import AuditLog
from api.models.user import User
from api.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserPublic

router = APIRouter()

_ACCESS_EXPIRE_SEC = settings.JWT_ACCESS_EXPIRE_MINUTES * 60


async def _audit(db: AsyncSession, action: str, user_id=None, ip=None, status="success", detail=None):
    db.add(AuditLog(
        user_id=user_id, action=action, ip_address=ip,
        status=status, detail=detail,
    ))


@router.post("/register", response_model=UserPublic, status_code=201)
async def register(body: RegisterRequest, request: Request, db: DB):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()
    await _audit(db, "register", user_id=user.id, ip=request.client.host if request.client else None)
    return UserPublic.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: DB):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    ip = request.client.host if request.client else None

    if not user or not verify_password(body.password, user.password_hash):
        await _audit(db, "login_failed", ip=ip, status="failed", detail=body.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    await _audit(db, "login", user_id=user.id, ip=ip)
    return TokenResponse(
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
    except (JWTError, ValueError, KeyError):
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

