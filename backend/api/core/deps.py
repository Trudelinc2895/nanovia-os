"""
backend/api/core/deps.py — FastAPI dependency injection
"""
from __future__ import annotations

import ipaddress
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.core.security import decode_token
from api.database import get_db
from api.models.user import User

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise credentials_exc

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise credentials_exc
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exc
    except InvalidTokenError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exc
    return user


async def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    from api.core.monetization._workspace import get_workspace, workspace_is_active

    workspace = await get_workspace(str(user.id), db)
    if workspace is None or not workspace_is_active(workspace):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace inactive",
        )
    return user


def require_plan(*plans: str):
    """Dependency factory: require user to have one of the given plans."""
    from api.core.monetization import getActivePlan

    async def _check(
        user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        active_plan = await getActivePlan(str(user.id), db)
        if active_plan not in plans:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires a plan upgrade: {' or '.join(plans)}",
            )
        return user
    return _check


def require_feature(feature: str):
    """Dependency factory: require server-computed entitlements for a feature."""
    from api.core.monetization import canUseFeature

    async def _check(
        user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        allowed = await canUseFeature(str(user.id), feature, db)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Fonctionnalité non disponible dans ton plan actuel. Upgrade requis.",
            )
        return user
    return _check


def require_subscription_active():
    """Require an active-like subscription state for paid access paths."""
    from api.services.billing_service import get_active_subscription
    from api.services.subscription_state_machine import is_access_granted

    async def _check(
        user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        sub = await get_active_subscription(user.id, db)
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Active subscription required.",
            )
        if not is_access_granted(sub):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription inactive. Update billing to restore access.",
            )
        return user

    return _check


def require_module_access(module_slug: str):
    """Require access to a module via plan inclusion or active module purchase."""
    from api.services.entitlements_service import has_module_access

    async def _check(
        user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        if not await has_module_access(user, module_slug, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module_slug}' not available on this account.",
            )
        return user

    return _check


def require_usage_budget(usage_type: str = "ai_message"):
    """Require remaining usage budget or successful overage-credit deduction."""
    from api.services.usage_service import check_and_charge_usage

    async def _check(
        user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> tuple[bool, str]:
        allowed, reason = await check_and_charge_usage(user, db, usage_type=usage_type)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Limite mensuelle atteinte. Upgrade ton plan pour continuer.",
            )
        return allowed, reason

    return _check


def _request_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        first_ip = forwarded_for.split(",", 1)[0].strip()
        if first_ip:
            return first_ip

    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip

    if request.client and request.client.host:
        return request.client.host
    return None


def _is_allowed_admin_ip(ip_text: str | None) -> bool:
    if not ip_text:
        return False
    try:
        ip_addr = ipaddress.ip_address(ip_text)
    except ValueError:
        return False

    for cidr in settings.ADMIN_ALLOWED_IPS:
        if ip_addr in ipaddress.ip_network(cidr, strict=False):
            return True
    return False


async def get_admin_user(
    user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
) -> User:
    """Require the user to have admin role (is_admin flag)."""
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    if (
        settings.APP_ENV == "production"
        and request.url.path.startswith("/api/v1/admin")
        and settings.ADMIN_ALLOWED_IPS
        and not _is_allowed_admin_ip(_request_client_ip(request))
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin network access required",
        )
    return user


# Typed aliases for cleaner route signatures
CurrentUser = Annotated[User, Depends(get_current_active_user)]
DB = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[User, Depends(get_admin_user)]


async def get_optional_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Returns the authenticated User or None if no valid token is present.

    Does NOT raise on missing/invalid credentials — callers decide what to do.
    """
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]
