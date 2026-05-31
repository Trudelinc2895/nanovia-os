from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from jwt.exceptions import InvalidTokenError

from api.config import settings
from api.core.security import decode_token
from api.services import model_policy, sandbox_service

_SECRET_PATTERNS = [
    re.compile(r"\bsk_(live|test|proj|svcacct|admin)[A-Za-z0-9\-_]+\b", re.IGNORECASE),
    re.compile(r"\bpk_(live|test)_[A-Za-z0-9]+\b", re.IGNORECASE),
    re.compile(r"\brk_[A-Za-z0-9_]+\b", re.IGNORECASE),
    re.compile(r"\b(?:ghp|github_pat|xoxb)-[A-Za-z0-9_\-]+\b", re.IGNORECASE),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{20,}\b"),
]
_EMAIL_PATTERN = re.compile(r"([A-Z0-9._%+-]+)@([A-Z0-9.-]+\.[A-Z]{2,})", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_TENANT_ID_PATTERN = re.compile(r"\b(?:tenant|workspace|customer|acct|org)_[A-Za-z0-9]+\b", re.IGNORECASE)
_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")


def ensure_tenant_isolation(request_tenant_id: str | None, profile_tenant_id: str | None) -> None:
    if not request_tenant_id or not profile_tenant_id or request_tenant_id != profile_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant isolation violation.")


def ensure_subscription_active(workspace: dict[str, Any]) -> None:
    blocked = bool(workspace.get("blocked"))
    status_value = str(workspace.get("subscription_status", "inactive")).lower()
    if blocked or status_value not in {"active", "trialing"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription inactive for AI access.")


def ensure_module_allowed(module_key: str, profile: dict[str, Any]) -> None:
    modules = set(profile.get("allowed_modules", []))
    if module_key not in modules:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Module '{module_key}' is not enabled for this tenant.")


def ensure_credits_available(workspace_id: str, credits_requested: int, plan: str) -> None:
    credits = sandbox_service.get_credits(workspace_id)
    if credits_requested > int(credits.get("remaining", 0)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient AI credits.")
    if int(credits.get("used", 0)) + credits_requested > int(model_policy.plan_policy(plan).get("max_monthly_credits", 0)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI monthly credit policy exceeded.")


def ensure_no_live_key_in_sandbox() -> None:
    if settings.APP_ENV != "sandbox":
        return
    candidates = [
        getattr(settings, "OPENAI_API_KEY", ""),
        getattr(settings, "STRIPE_SECRET_KEY", ""),
        getattr(settings, "STRIPE_PUBLIC_KEY", ""),
    ]
    if any(str(value).startswith(("sk_live_", "pk_live_")) for value in candidates if value):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Live OpenAI or Stripe key refused in sandbox.")


def ensure_no_secret_in_memory(content: str) -> None:
    if any(pattern.search(content or "") for pattern in _SECRET_PATTERNS):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Secrets cannot be stored in AI memory.")


def ensure_master_access_only(master_context: bool) -> None:
    if not master_context:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Master context required.")


def ensure_safe_identifier(value: str, *, field_name: str) -> str:
    cleaned = (value or "").strip()
    if not _SAFE_IDENTIFIER_PATTERN.fullmatch(cleaned):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsafe {field_name}.")
    return cleaned


def authenticate_access_token(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.")
    if payload.get("type") != "access" or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.")
    return payload


def ensure_actor_matches_claim(user_id: str | None, claims: dict[str, Any]) -> str:
    subject = str(claims.get("sub"))
    if user_id and user_id != subject:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User context mismatch.")
    return subject


def ensure_master_identity(master_context: bool, claims: dict[str, Any], admin_key: str | None) -> str:
    ensure_master_access_only(master_context)
    if not bool(claims.get("is_admin", False)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    configured_key = str(getattr(settings, "AI_ADMIN_API_KEY", "") or "").strip()
    if configured_key and admin_key != configured_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid AI admin key.")
    return str(claims.get("sub"))


def resolve_tenant_access(
    claims: dict[str, Any],
    *,
    requested_tenant_id: str | None = None,
    requested_workspace_id: str | None = None,
) -> tuple[str, str]:
    claimed_workspace_id = ensure_safe_identifier(str(claims.get("workspace_id") or ""), field_name="workspace_id")
    claimed_tenant_id = str(claims.get("tenant_id") or claimed_workspace_id)
    claimed_tenant_id = ensure_safe_identifier(claimed_tenant_id, field_name="tenant_id")

    if requested_workspace_id and ensure_safe_identifier(requested_workspace_id, field_name="workspace_id") != claimed_workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied.")
    if requested_tenant_id and ensure_safe_identifier(requested_tenant_id, field_name="tenant_id") != claimed_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied.")

    return claimed_tenant_id, claimed_workspace_id


def anonymize_learning_event(content: str) -> str:
    value = _EMAIL_PATTERN.sub("[redacted-email]", content or "")
    value = _PHONE_PATTERN.sub("[redacted-phone]", value)
    value = _TENANT_ID_PATTERN.sub("[redacted-tenant-id]", value)
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[redacted-secret]", value)
    return " ".join(value.split())
