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
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from api.config import get_runtime_settings_snapshot, reload_runtime_settings
from api.core.monetization import getEntitlements as monetization_get_entitlements
from api.core.monetization import getUsageSnapshot as monetization_get_usage_snapshot
from api.core.monetization._workspace import ensure_owner_workspace, get_workspace
from api.core.deps import AdminUser, DB
from api.models.audit import AuditLog
from api.models.credit_ledger import CreditLedger
from api.models.subscription import Subscription
from api.models.user import User
from api.models.webhook_event import WebhookEvent
from api.models.workspace_billing import CreditBalance, Invoice, Member, UsageEvent, Workspace
from api.services.billing_service import (
    PLANS_CONFIG,
    get_webhook_event,
    process_stripe_event,
    update_webhook_status,
)
from api.services.credit_service import adjust_credits
from api.services.subscription_state_machine import is_access_granted

logger = logging.getLogger(__name__)
router = APIRouter()


def _sanitize_log_value(value: str | None) -> str:
    """Prevent CRLF-based log injection in operator-controlled fields."""
    return (value or "").replace("\n", " ").replace("\r", " ")


# ─── Request schemas ──────────────────────────────────────────────────────────

class CreditAdjustRequest(BaseModel):
    amount: int  # positive = add, negative = remove
    note: str | None = None
    idempotency_key: str | None = None  # optional: prevents double-submit


class PlanOverrideRequest(BaseModel):
    plan: str
    reason: str | None = None


class WebhookReprocessRequest(BaseModel):
    force: bool = False


class WorkspaceStatusRequest(BaseModel):
    blocked: bool
    reason: str | None = None


class WorkspacePlanOverrideRequest(BaseModel):
    plan: str
    reason: str | None = None


class RuntimeConfigReloadRequest(BaseModel):
    dry_run: bool = False


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
            idempotency_key=body.idempotency_key,
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
    safe_old_plan = _sanitize_log_value(old_plan)
    safe_new_plan = _sanitize_log_value(body.plan)
    safe_reason = _sanitize_log_value(body.reason)
    logger.info("[admin] Plan override user=%s %s→%s by admin=%s reason=%s",
                user_id, safe_old_plan, safe_new_plan, admin.email, safe_reason)
    return {"status": "ok", "old_plan": old_plan, "new_plan": body.plan}


@router.get("/runtime-config")
async def admin_get_runtime_config(admin: AdminUser):
    """Expose the currently reloadable runtime settings without sensitive fields."""
    return get_runtime_settings_snapshot()


@router.post("/runtime-config/reload")
async def admin_reload_runtime_config(
    body: RuntimeConfigReloadRequest,
    admin: AdminUser,
):
    """Reload only non-critical runtime settings that are safe to mutate in-process."""
    result = reload_runtime_settings(dry_run=body.dry_run)
    logger.info(
        "[admin] Runtime config reload dry_run=%s changed=%s by admin=%s",
        body.dry_run,
        ",".join(sorted(result["changed"])),
        admin.email,
    )
    return result


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


@router.get("/workspaces")
async def admin_list_workspaces(
    admin: AdminUser,
    db: DB,
    page: int = 1,
    per_page: int = 50,
):
    """List compatibility workspaces with owner, plan, credit, and member counts."""
    users_result = await db.execute(select(User))
    for user in users_result.scalars().all():
        await ensure_owner_workspace(user, db)

    offset = (page - 1) * per_page
    result = await db.execute(
        select(Workspace)
        .order_by(Workspace.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    workspaces = result.scalars().all()

    count_result = await db.execute(select(func.count(Workspace.id)))
    total = count_result.scalar_one()

    items: list[dict] = []
    for workspace in workspaces:
        owner_result = await db.execute(select(User).where(User.id == workspace.owner_user_id))
        owner = owner_result.scalar_one_or_none()
        balance_result = await db.execute(
            select(CreditBalance).where(CreditBalance.workspace_id == workspace.id)
        )
        credit_balance = balance_result.scalar_one_or_none()
        member_count_result = await db.execute(
            select(func.count(Member.id)).where(Member.workspace_id == workspace.id)
        )
        items.append(
            {
                "id": str(workspace.id),
                "name": workspace.name,
                "status": workspace.status,
                "active_plan_key": workspace.active_plan_key,
                "billing_email": workspace.billing_email,
                "credit_balance": (
                    credit_balance.balance if credit_balance is not None else int(owner.credits or 0) if owner else 0
                ),
                "owner": {
                    "id": str(owner.id) if owner else None,
                    "email": owner.email if owner else None,
                    "full_name": owner.full_name if owner else None,
                    "is_active": owner.is_active if owner else None,
                    "credits": owner.credits if owner else None,
                },
                "member_count": member_count_result.scalar_one(),
                "created_at": workspace.created_at.isoformat(),
            }
        )

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "workspaces": items,
    }


@router.get("/workspaces/{workspace_id}")
async def admin_get_workspace(
    workspace_id: uuid.UUID,
    admin: AdminUser,
    db: DB,
):
    """Get a workspace detail including entitlements, usage, and owner state."""
    workspace = await get_workspace(workspace_id, db)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    owner_result = await db.execute(select(User).where(User.id == workspace.owner_user_id))
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=404, detail="Workspace owner not found")

    balance_result = await db.execute(
        select(CreditBalance).where(CreditBalance.workspace_id == workspace.id)
    )
    credit_balance = balance_result.scalar_one_or_none()
    member_rows = await db.execute(
        select(Member)
        .where(Member.workspace_id == workspace_id)
        .order_by(Member.invited_at.desc())
    )
    entitlements = await monetization_get_entitlements(str(workspace_id), db)
    usage = await monetization_get_usage_snapshot(str(workspace_id), db)

    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "status": workspace.status,
        "active_plan_key": workspace.active_plan_key,
        "billing_email": workspace.billing_email,
        "credit_balance": (
            credit_balance.balance if credit_balance is not None else int(owner.credits or 0)
        ),
        "owner": {
            "id": str(owner.id),
            "email": owner.email,
            "full_name": owner.full_name,
            "is_active": owner.is_active,
            "credits": owner.credits,
            "plan": owner.plan,
        },
        "members": [
            {
                "id": str(member.id),
                "email": member.email,
                "role": member.role,
                "status": member.status,
                "user_id": str(member.user_id) if member.user_id else None,
            }
            for member in member_rows.scalars().all()
        ],
        "entitlements": entitlements,
        "usage": usage,
    }


@router.post("/workspaces/{workspace_id}/credits")
async def admin_adjust_workspace_credits(
    workspace_id: uuid.UUID,
    body: CreditAdjustRequest,
    admin: AdminUser,
    db: DB,
):
    """Adjust the compatibility workspace credit balance through the owner ledger."""
    workspace = await get_workspace(workspace_id, db)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        entry = await adjust_credits(
            user_id=workspace.owner_user_id,
            amount=body.amount,
            source=f"admin-workspace:{admin.email}",
            db=db,
            note=body.note or f"Workspace credit adjustment by {admin.email}",
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "status": "ok",
        "workspace_id": str(workspace_id),
        "amount": body.amount,
        "balance_after": entry.balance_after,
    }


@router.put("/workspaces/{workspace_id}/status")
async def admin_update_workspace_status(
    workspace_id: uuid.UUID,
    body: WorkspaceStatusRequest,
    admin: AdminUser,
    db: DB,
):
    """Block or unblock a workspace by syncing workspace.status and owner activation."""
    workspace = await get_workspace(workspace_id, db)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    owner_result = await db.execute(select(User).where(User.id == workspace.owner_user_id))
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=404, detail="Workspace owner not found")

    workspace.status = "blocked" if body.blocked else "active"
    owner.is_active = not body.blocked
    db.add(workspace)
    db.add(owner)
    await db.commit()

    logger.info(
        "[admin] Workspace status updated workspace=%s blocked=%s by admin=%s reason=%s",
        workspace_id,
        body.blocked,
        admin.email,
        _sanitize_log_value(body.reason),
    )
    return {
        "status": "ok",
        "workspace_id": str(workspace_id),
        "workspace_status": workspace.status,
        "owner_is_active": owner.is_active,
    }


@router.put("/workspaces/{workspace_id}/plan")
async def admin_override_workspace_plan(
    workspace_id: uuid.UUID,
    body: WorkspacePlanOverrideRequest,
    admin: AdminUser,
    db: DB,
):
    """Force a workspace entitlement plan through the compatibility owner account."""
    if body.plan not in PLANS_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan!r}")

    workspace = await get_workspace(workspace_id, db)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    owner_result = await db.execute(select(User).where(User.id == workspace.owner_user_id))
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=404, detail="Workspace owner not found")

    old_plan = owner.plan
    owner.plan = body.plan
    workspace.active_plan_key = body.plan
    db.add(owner)
    db.add(workspace)
    await db.commit()

    logger.info(
        "[admin] Workspace plan override workspace=%s %s→%s by admin=%s reason=%s",
        workspace_id,
        _sanitize_log_value(old_plan),
        _sanitize_log_value(body.plan),
        admin.email,
        _sanitize_log_value(body.reason),
    )
    return {
        "status": "ok",
        "workspace_id": str(workspace_id),
        "old_plan": old_plan,
        "new_plan": body.plan,
    }


@router.post("/webhooks/{stripe_event_id}/reprocess")
async def admin_reprocess_webhook(
    stripe_event_id: str,
    admin: AdminUser,
    db: DB,
    body: WebhookReprocessRequest | None = None,
):
    """Re-fetch a stored Stripe event and re-apply it for operator recovery."""
    stored_event = await get_webhook_event(stripe_event_id, db)
    if not stored_event:
        raise HTTPException(status_code=404, detail="Webhook event not found")

    force = body.force if body else False
    if stored_event.status == "processing":
        raise HTTPException(status_code=409, detail="Webhook event is already processing")
    if stored_event.status == "processed" and not force:
        raise HTTPException(
            status_code=409,
            detail="Webhook event already processed; retry with force=true to replay",
        )

    try:
        stripe_event = stripe.Event.retrieve(stripe_event_id)
    except stripe.StripeError as exc:
        raise HTTPException(status_code=502, detail=f"Stripe event fetch failed: {exc}") from exc

    if stripe_event["id"] != stripe_event_id:
        raise HTTPException(status_code=502, detail="Stripe returned mismatched event id")
    if stripe_event["type"] != stored_event.event_type:
        raise HTTPException(
            status_code=409,
            detail="Stored webhook event type does not match Stripe event type",
        )

    await update_webhook_status(stripe_event_id, "processing", None, db)

    try:
        final_status = await process_stripe_event(
            stripe_event["type"],
            stripe_event["data"]["object"],
            db,
        )
    except Exception as exc:
        await update_webhook_status(stripe_event_id, "failed", str(exc), db)
        logger.exception(
            "[admin] Webhook reprocess failed event=%s by admin=%s",
            stripe_event_id,
            admin.email,
        )
        raise HTTPException(status_code=502, detail=f"Webhook reprocess failed: {exc}") from exc

    await update_webhook_status(stripe_event_id, final_status, None, db)
    logger.info(
        "[admin] Webhook reprocessed event=%s by admin=%s status=%s force=%s",
        stripe_event_id,
        admin.email,
        final_status,
        force,
    )
    return {
        "status": final_status,
        "stripe_event_id": stripe_event_id,
        "event_type": stored_event.event_type,
        "forced": force,
    }


@router.get("/users/{user_id}/billing-audit")
async def admin_get_billing_audit(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DB,
    limit: int = 50,
):
    """Return recent billing audit entries for a user."""
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.user_id == user_id,
            AuditLog.resource == "billing",
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return {
        "audit_logs": [
            {
                "id": str(row.id),
                "action": row.action,
                "status": row.status,
                "detail": row.detail,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.post("/users/{user_id}/resync-subscription")
async def admin_resync_subscription(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DB,
):
    """Force-sync the user's latest Stripe subscription state into local DB."""
    from api.services.billing_service import resync_user_subscription_from_stripe

    try:
        result = await resync_user_subscription_from_stripe(user_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("[admin] Billing resync failed for user=%s by admin=%s", user_id, admin.email)
        raise HTTPException(status_code=502, detail=f"Stripe resync failed: {exc}")

    logger.info("[admin] Billing resync user=%s by admin=%s status=%s", user_id, admin.email, result["status"])
    return result


@router.get("/metrics")
async def admin_metrics(admin: AdminUser, db: DB):
    """Aggregate business metrics and a lightweight FinOps summary."""
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

    window_start = datetime.now(timezone.utc) - timedelta(days=30)

    subscription_rows = (
        await db.execute(select(Subscription).where(Subscription.plan.in_(("pro", "business"))))
    ).scalars().all()
    active_paid_subscriptions = [sub for sub in subscription_rows if is_access_granted(sub)]
    active_paid = len(active_paid_subscriptions)
    estimated_mrr = 0.0
    for sub in active_paid_subscriptions:
        plan_cfg = PLANS_CONFIG.get(sub.plan, {})
        if (sub.billing_interval or "monthly") == "yearly":
            estimated_mrr += float(plan_cfg.get("price_yearly_usd", 0)) / 12.0
        else:
            estimated_mrr += float(plan_cfg.get("price_monthly_usd", 0))

    paid_invoices = (
        await db.execute(
            select(Invoice.workspace_id, func.coalesce(func.sum(Invoice.total_cents), 0).label("revenue_cents"))
            .where(Invoice.status == "paid", Invoice.paid_at.is_not(None), Invoice.paid_at >= window_start)
            .group_by(Invoice.workspace_id)
        )
    ).all()
    revenue_by_workspace = {
        str(row.workspace_id): float(row.revenue_cents or 0) / 100.0
        for row in paid_invoices
    }
    trailing_30d_revenue = sum(revenue_by_workspace.values())

    usage_cost_rows = (
        await db.execute(
            select(UsageEvent.workspace_id, func.coalesce(func.sum(UsageEvent.cost_usd), 0).label("usage_cost"))
            .where(UsageEvent.created_at >= window_start)
            .group_by(UsageEvent.workspace_id)
        )
    ).all()
    usage_cost_by_workspace = {
        str(row.workspace_id): float(row.usage_cost or 0)
        for row in usage_cost_rows
    }
    trailing_30d_usage_cost = sum(usage_cost_by_workspace.values())

    workspace_rows = (await db.execute(select(Workspace.id, Workspace.name))).all()
    workspace_names = {str(row.id): row.name for row in workspace_rows}
    all_workspace_ids = set(workspace_names) | set(revenue_by_workspace) | set(usage_cost_by_workspace)
    workspace_margin_rows = []
    for workspace_id in all_workspace_ids:
        revenue_usd = revenue_by_workspace.get(workspace_id, 0.0)
        cost_usd = usage_cost_by_workspace.get(workspace_id, 0.0)
        margin_usd = revenue_usd - cost_usd
        workspace_margin_rows.append(
            {
                "workspace_id": workspace_id,
                "name": workspace_names.get(workspace_id, "unknown"),
                "trailing_30d_revenue_usd": round(revenue_usd, 2),
                "trailing_30d_usage_cost_usd": round(cost_usd, 2),
                "trailing_30d_margin_usd": round(margin_usd, 2),
            }
        )
    top_unprofitable_workspaces = sorted(
        (row for row in workspace_margin_rows if row["trailing_30d_margin_usd"] < 0),
        key=lambda row: row["trailing_30d_margin_usd"],
    )[:5]

    cancelled_last_30d = (
        await db.execute(
            select(func.count(Subscription.id)).where(
                Subscription.plan.in_(("pro", "business")),
                Subscription.status.in_(("canceled", "cancelled")),
                Subscription.updated_at >= window_start,
            )
        )
    ).scalar_one()
    churn_rate = (
        round(cancelled_last_30d / active_paid, 4)
        if active_paid
        else None
    )
    arpu_mrr = (estimated_mrr / active_paid) if active_paid else None
    ltv_estimate = (
        round(arpu_mrr / churn_rate, 2)
        if arpu_mrr is not None and churn_rate not in (None, 0)
        else None
    )

    return {
        "total_users": total_users,
        "users_by_plan": plans,
        "active_paid_users": active_paid,
        "subscriptions_by_status": subs,
        "estimated_mrr_usd": round(estimated_mrr, 2),
        "trailing_30d_revenue_usd": round(trailing_30d_revenue, 2),
        "trailing_30d_usage_cost_usd": round(trailing_30d_usage_cost, 2),
        "trailing_30d_gross_margin_usd": round(trailing_30d_revenue - trailing_30d_usage_cost, 2),
        "top_unprofitable_workspaces": top_unprofitable_workspaces,
        "churn_rate_30d": churn_rate,
        "ltv_estimate_usd": ltv_estimate,
        "cac_estimate_usd": None,
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
    from api.services.module_registry import canonicalize_module_slug
    user_id = body.get("user_id")
    module_slug = canonicalize_module_slug(body.get("module_slug"))
    if not user_id or not module_slug:
        raise HTTPException(status_code=400, detail="user_id and module_slug required")
    await activate_user_module(user_id, module_slug, None, None, db)
    return {"granted": True, "user_id": user_id, "module_slug": module_slug}


@router.post("/module-access/revoke")
async def admin_revoke_module(body: dict, admin: AdminUser, db: DB):
    """Manually revoke a module from a user. Body: {user_id, module_slug}"""
    from api.models.user_module import UserModule as _UM
    from api.services.module_registry import canonicalize_module_slug, get_module_lookup_slugs
    from sqlalchemy import select as _sel
    user_id = body.get("user_id")
    module_slug = canonicalize_module_slug(body.get("module_slug"))
    if not user_id or not module_slug:
        raise HTTPException(status_code=400, detail="user_id and module_slug required")
    lookup_slugs = get_module_lookup_slugs(module_slug)
    result = await db.execute(
        _sel(_UM).where(
            _UM.user_id == uuid.UUID(user_id),
            _UM.module_slug.in_(lookup_slugs),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Module access not found")
    row.module_slug = module_slug
    row.status = "cancelled"
    await db.commit()
    return {"revoked": True, "user_id": user_id, "module_slug": module_slug}
