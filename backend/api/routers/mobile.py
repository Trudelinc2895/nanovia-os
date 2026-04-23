"""
backend/api/routers/mobile.py

Endpoints dédiés au client mobile :
  GET  /modules/catalog        → catalogue modules avec visible_on_mobile
  GET  /modules/me             → modules accessibles par l'user (entitlements)
  GET  /users/me/sessions      → sessions actives (device tracking)
  DELETE /users/me/sessions/{id} → révoquer une session (kill switch)
  POST /notifications/register-device → enregistrer push token
  GET  /notifications/me       → notifications non lues
  PATCH /notifications/{id}/read → marquer lue
  GET  /vip/overview           → KPIs + alertes (role=vip ou admin)
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.core.data_protection import encrypt_at_rest
from api.core.deps import CurrentUser, DB
from api.models.device_session import DeviceSession
from api.models.notification import UserNotification
from api.services.billing_service import MODULES_CONFIG, compute_entitlements, get_active_subscription
from api.services.entitlements_service import has_module_access
from api.services.module_registry import MODULE_REGISTRY_SLUGS, get_module_registry_entry
from api.services.subscription_state_machine import is_access_granted

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_module_entry(module_meta: dict[str, Any], is_available: bool) -> dict[str, Any]:
    module_cfg = MODULES_CONFIG[module_meta["slug"]]
    return {
        "key": module_meta["key"],
        "slug": module_meta["slug"],
        "name": module_cfg["name"],
        "description": module_cfg["description"],
        "category": module_meta["category"],
        "icon": module_meta["icon"],
        "enabled": module_meta["enabled"],
        "visible_on_mobile": module_meta["visible_on_mobile"],
        "entitlements_required": list(module_cfg.get("included_in_plans", [])),
        "roles_allowed": module_meta["roles_allowed"],
        "is_available": is_available,
    }


async def _build_mobile_catalog(current_user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for module_slug in MODULE_REGISTRY_SLUGS:
        module_meta = get_module_registry_entry(module_slug)
        if not module_meta:
            continue
        is_available = module_meta["enabled"] and await has_module_access(
            current_user,
            module_slug,
            db,
        )
        catalog.append(_serialize_module_entry(module_meta, is_available))
    return catalog


async def _require_vip_access(current_user: CurrentUser, db: DB) -> tuple[dict[str, Any], Any]:
    sub = await get_active_subscription(current_user.id, db)
    entitlements = compute_entitlements(current_user, sub)

    if getattr(current_user, "is_admin", False):
        return entitlements, sub

    if entitlements["plan"] == "free":
        raise HTTPException(status_code=403, detail="VIP access requires a paid plan")
    if not is_access_granted(sub):
        raise HTTPException(status_code=402, detail="Active subscription required.")

    return entitlements, sub


# ─── Module catalog ───────────────────────────────────────────────────────────

@router.get("/modules/catalog")
async def get_modules_catalog(current_user: CurrentUser, db: DB):
    """Full module catalog with user access computed per module."""
    return await _build_mobile_catalog(current_user, db)


@router.get("/modules/catalog/mobile")
async def get_mobile_modules(current_user: CurrentUser, db: DB):
    """Modules visible_on_mobile only — for the mobile client."""
    catalog = await _build_mobile_catalog(current_user, db)
    return [module for module in catalog if module["visible_on_mobile"]]


@router.get("/modules/me")
async def get_my_modules(current_user: CurrentUser, db: DB):
    """Modules the current user has access to (enabled + entitlement/module check)."""
    catalog = await _build_mobile_catalog(current_user, db)
    return [module for module in catalog if module["enabled"] and module["is_available"]]


# ─── Sessions (device tracking + kill switch) ─────────────────────────────────

class DeviceRegistrationRequest(BaseModel):
    push_token: str = Field(..., min_length=10)
    device_id: str = Field(..., min_length=10)
    device_name: str = Field(default="Mobile", max_length=255)
    platform: str = Field(default="ios", pattern="^(ios|android|web)$")


@router.post("/notifications/register-device", status_code=status.HTTP_201_CREATED)
async def register_device(body: DeviceRegistrationRequest, current_user: CurrentUser, db: DB, request: Request):
    """Register or update push token for a device. Idempotent by device_id."""
    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.user_id == current_user.id,
            DeviceSession.device_id == body.device_id,
        )
    )
    session = result.scalar_one_or_none()

    ip = request.client.host if request.client else None

    if session is None:
        session = DeviceSession(
            user_id=current_user.id,
            device_id=body.device_id,
            device_name=body.device_name,
            platform=body.platform,
            push_token=encrypt_at_rest(body.push_token),
            ip_address=ip,
        )
        db.add(session)
    else:
        session.push_token = encrypt_at_rest(body.push_token)
        session.device_name = body.device_name
        session.last_seen = datetime.now(timezone.utc)
        session.ip_address = ip
        session.is_active = True

    await db.commit()
    return {"registered": True, "device_id": body.device_id}


@router.get("/users/me/sessions")
async def get_my_sessions(current_user: CurrentUser, db: DB):
    """List all active device sessions for the current user."""
    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.user_id == current_user.id,
            DeviceSession.is_active == True,  # noqa: E712
        ).order_by(DeviceSession.last_seen.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "device_id": s.device_id,
            "device_name": s.device_name,
            "platform": s.platform,
            "ip_address": s.ip_address,
            "last_seen": s.last_seen.isoformat(),
        }
        for s in sessions
    ]


@router.delete("/users/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: str, current_user: CurrentUser, db: DB):
    """Revoke (kill) a device session. Users can only revoke their own."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.id == sid,
            DeviceSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_active = False
    await db.commit()


# ─── Notifications ────────────────────────────────────────────────────────────

@router.get("/notifications/me")
async def get_my_notifications(current_user: CurrentUser, db: DB):
    """Return last 50 notifications for current user."""
    result = await db.execute(
        select(UserNotification)
        .where(UserNotification.user_id == current_user.id)
        .order_by(UserNotification.created_at.desc())
        .limit(50)
    )
    notifs = result.scalars().all()
    return [
        {
            "id": str(n.id),
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "read": n.read,
            "data": n.data,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifs
    ]


@router.patch("/notifications/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_notification_read(notification_id: str, current_user: CurrentUser, db: DB):
    """Mark a notification as read."""
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification ID")

    result = await db.execute(
        select(UserNotification).where(
            UserNotification.id == nid,
            UserNotification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.read = True
    await db.commit()
    return {"read": True}


# ─── VIP Panel ────────────────────────────────────────────────────────────────

@router.get("/vip/overview")
async def get_vip_overview(current_user: CurrentUser, db: DB):
    """VIP dashboard — KPIs + alerts. Requires vip or admin role."""
    entitlements, sub = await _require_vip_access(current_user, db)

    from api.services.usage_service import get_monthly_usage
    usage = await get_monthly_usage(current_user.id, db)

    msg_limit = entitlements["limits"]["ai_messages_per_month"]
    msg_used = usage.get("messages_count", 0)
    msg_display = "∞" if msg_limit == -1 else str(msg_limit)
    trend = "stable"
    if msg_limit != -1 and msg_limit > 0:
        ratio = msg_used / msg_limit
        trend = "warning" if ratio >= 0.8 else ("critical" if ratio >= 1.0 else "stable")

    kpis = [
        {
            "key": "plan",
            "label": "Plan actuel",
            "value": str(entitlements["plan"]).upper(),
            "trend": "stable",
        },
        {
            "key": "messages_used",
            "label": "Messages utilisés ce mois",
            "value": msg_used,
            "limit": msg_display,
            "unit": "msgs",
            "trend": trend,
        },
        {
            "key": "tokens_used",
            "label": "Tokens consommés",
            "value": usage.get("tokens_total", 0),
            "unit": "tokens",
            "trend": "stable",
        },
        {
            "key": "cost_usd",
            "label": "Coût IA ce mois",
            "value": round(usage.get("cost_usd_total", 0.0), 4),
            "unit": "USD",
            "trend": "stable",
        },
        {
            "key": "modules_available",
            "label": "Modules actifs",
            "value": entitlements["limits"]["active_modules"],
            "unit": "modules",
            "trend": "stable",
        },
        {
            "key": "credits",
            "label": "Crédits disponibles",
            "value": getattr(current_user, "credits", 0),
            "unit": "crédits",
            "trend": "stable",
        },
    ]

    alerts = []
    if sub and sub.status == "past_due":
        alerts.append({
            "id": "billing-past-due",
            "severity": "critical",
            "message": "Paiement en retard — mettre à jour ta carte de crédit",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    return {
        "kpis": kpis,
        "alerts": alerts,
        "subscription": {
            "status": sub.status if sub else "free",
            "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        },
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/vip/kpis")
async def get_vip_kpis(current_user: CurrentUser, db: DB):
    """KPIs synthétiques — usage des modules, progression."""
    entitlements, _sub = await _require_vip_access(current_user, db)
    return {"kpis": [
        {"key": "plan", "label": "Plan", "value": entitlements["plan"], "trend": "stable"},
        {"key": "active_modules", "label": "Modules", "value": entitlements["limits"]["active_modules"]},
        {"key": "ai_messages", "label": "Msgs/mois", "value": entitlements["limits"]["ai_messages_per_month"]},
    ]}
