"""backend/api/routers/admin.py — Internal admin/ops endpoints.

All routes require admin authentication (is_admin=True on User).
Never expose these routes publicly without IP allowlisting in production.

Endpoints:
  GET  /admin/users             — list all users with plan/usage/credits
  GET  /admin/users/{user_id}   — user detail with subscription + ledger
  POST /admin/users/{user_id}/credits  — add/remove credits (adjustment)
  PUT  /admin/users/{user_id}/plan     — override user plan
  GET  /admin/webhooks          — recent webhook events (with status)
  GET  /admin/metrics           — MRR, user counts, plan distribution
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from markupsafe import escape
from pydantic import BaseModel
from sqlalchemy import func, select

from api.core.deps import AdminUser, DB
from api.models.credit_ledger import CreditLedger
from api.models.subscription import Subscription
from api.models.user import User
from api.models.webhook_event import WebhookEvent
from api.services.billing_service import PLANS_CONFIG
from api.services.credit_service import adjust_credits

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Request schemas ──────────────────────────────────────────────────────────

class CreditAdjustRequest(BaseModel):
    amount: int  # positive = add, negative = remove
    note: str | None = None


class PlanOverrideRequest(BaseModel):
    plan: str
    reason: str | None = None


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/users")
async def admin_list_users(
    admin: AdminUser,
    db: DB,
    page: int = 1,
    per_page: int = 50,
):
    """List all users with plan, credit balance, and subscription status."""
    offset = (page - 1) * per_page
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    users = result.scalars().all()

    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar_one()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "plan": u.plan,
                "credits": u.credits,
                "is_active": u.is_active,
                "is_admin": getattr(u, "is_admin", False),
                "stripe_customer_id": u.stripe_customer_id,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
    }


@router.get("/users/{user_id}")
async def admin_get_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DB,
):
    """Get user detail including subscription and recent credit ledger."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sub_result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = sub_result.scalar_one_or_none()

    # Credit ledger history (CreditLedger imported at top of file)
    ledger_result = await db.execute(
        select(CreditLedger)
        .where(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.created_at.desc())
        .limit(20)
    )
    ledger = [
        {
            "type": e.type, "amount": e.amount,
            "balance_after": e.balance_after, "source": e.source,
            "note": e.note, "created_at": e.created_at.isoformat(),
        }
        for e in ledger_result.scalars().all()
    ]

    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "plan": user.plan,
        "credits": user.credits,
        "is_active": user.is_active,
        "is_admin": getattr(user, "is_admin", False),
        "stripe_customer_id": user.stripe_customer_id,
        "created_at": user.created_at.isoformat(),
        "subscription": {
            "plan": sub.plan if sub else None,
            "status": sub.status if sub else None,
            "billing_interval": sub.billing_interval if sub else None,
            "current_period_end": (sub.current_period_end.isoformat() if sub and sub.current_period_end else None),
            "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
            "trial_end": (sub.trial_end.isoformat() if sub and getattr(sub, "trial_end", None) else None),
        } if sub else None,
        "credit_ledger": ledger,
    }


@router.post("/users/{user_id}/credits")
async def admin_adjust_credits(
    user_id: uuid.UUID,
    body: CreditAdjustRequest,
    admin: AdminUser,
    db: DB,
):
    """Admin-initiated credit adjustment. Recorded in ledger with admin source."""
    try:
        entry = await adjust_credits(
            user_id=user_id,
            amount=body.amount,
            source=f"admin:{admin.email}",
            db=db,
            note=body.note or f"Admin adjustment by {admin.email}",
        )
        logger.info("[admin] Credit adjustment %+d for user=%s by admin=%s", body.amount, user_id, admin.email)
        return {
            "status": "ok",
            "amount": body.amount,
            "balance_after": entry.balance_after,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/users/{user_id}/plan")
async def admin_override_plan(
    user_id: uuid.UUID,
    body: PlanOverrideRequest,
    admin: AdminUser,
    db: DB,
):
    """Override user plan directly (admin bypass — use for comps, corrections, etc.)."""
    if body.plan not in PLANS_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan!r}")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_plan = user.plan
    user.plan = body.plan
    db.add(user)
    await db.commit()
    # Sanitize free-text fields before logging to prevent log injection (CRLF)
    safe_reason = (body.reason or "").replace("\n", " ").replace("\r", " ")
    logger.info("[admin] Plan override user=%s %s→%s by admin=%s reason=%s",
                user_id, old_plan, body.plan, admin.email, safe_reason)
    return {"status": "ok", "old_plan": old_plan, "new_plan": body.plan}


@router.get("/webhooks")
async def admin_list_webhooks(admin: AdminUser, db: DB, limit: int = 50):
    """List recent Stripe webhook events with processing status."""
    result = await db.execute(
        select(WebhookEvent)
        .order_by(WebhookEvent.processed_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return {
        "webhooks": [
            {
                "id": str(e.id),
                "stripe_event_id": e.stripe_event_id,
                "event_type": e.event_type,
                "status": e.status,
                "error": e.error,
                "processed_at": e.processed_at.isoformat() if e.processed_at else None,
            }
            for e in events
        ]
    }


@router.get("/metrics")
async def admin_metrics(admin: AdminUser, db: DB):
    """Aggregate business metrics: user counts by plan, subscription stats."""
    # Users by plan
    plan_result = await db.execute(
        select(User.plan, func.count(User.id).label("count"))
        .where(User.is_active == True)  # noqa: E712
        .group_by(User.plan)
    )
    plans = {row.plan: row.count for row in plan_result.all()}

    # Active subscriptions
    sub_result = await db.execute(
        select(Subscription.status, func.count(Subscription.id).label("count"))
        .group_by(Subscription.status)
    )
    subs = {row.status: row.count for row in sub_result.all()}

    # Total users
    total_result = await db.execute(select(func.count(User.id)))
    total_users = total_result.scalar_one()

    active_paid = plans.get("pro", 0) + plans.get("business", 0)

    return {
        "total_users": total_users,
        "users_by_plan": plans,
        "active_paid_users": active_paid,
        "subscriptions_by_status": subs,
        "estimated_mrr_usd": (plans.get("pro", 0) * 29) + (plans.get("business", 0) * 99),
    }


@router.get("/module-access/{user_id}")
async def get_module_access(user_id: str, admin: AdminUser, db: DB):
    """List all module accesses for a user (plan-included + purchased)."""
    from api.models.user_module import UserModule as _UM
    from sqlalchemy import select as _sel
    result = await db.execute(
        _sel(_UM).where(_UM.user_id == uuid.UUID(user_id))
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "module_slug": r.module_slug,
            "status": r.status,
            "stripe_subscription_id": r.stripe_subscription_id,
            "activated_at": r.activated_at.isoformat() if r.activated_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in rows
    ]


@router.post("/module-access/grant")
async def admin_grant_module(body: dict, admin: AdminUser, db: DB):
    """Manually grant a module to a user. Body: {user_id, module_slug}"""
    from api.services.billing_service import activate_user_module
    user_id = body.get("user_id")
    module_slug = body.get("module_slug")
    if not user_id or not module_slug:
        raise HTTPException(status_code=400, detail="user_id and module_slug required")
    await activate_user_module(user_id, module_slug, None, None, db)
    return {"granted": True, "user_id": user_id, "module_slug": module_slug}


@router.post("/module-access/revoke")
async def admin_revoke_module(body: dict, admin: AdminUser, db: DB):
    """Manually revoke a module from a user. Body: {user_id, module_slug}"""
    from api.models.user_module import UserModule as _UM
    from sqlalchemy import select as _sel
    user_id = body.get("user_id")
    module_slug = body.get("module_slug")
    if not user_id or not module_slug:
        raise HTTPException(status_code=400, detail="user_id and module_slug required")
    result = await db.execute(
        _sel(_UM).where(
            _UM.user_id == uuid.UUID(user_id),
            _UM.module_slug == module_slug,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Module access not found")
    row.status = "cancelled"
    await db.commit()
    return {"revoked": True, "user_id": user_id, "module_slug": module_slug}
