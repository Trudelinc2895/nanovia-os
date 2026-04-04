"""
backend/api/services/billing_service.py

Single source of truth for all monetization logic:
- Plan config (never trust client-side values)
- Stripe customer management
- Subscription sync from webhook events
- Entitlement computation from DB state
- Webhook idempotency
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models.subscription import Subscription
from api.models.user import User
from api.models.webhook_event import WebhookEvent

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


# ─── Plan configuration — server-side ONLY, never from client ────────────────
def _build_plans() -> dict[str, dict]:
    return {
        "free": {
            "name": "Free",
            "price_monthly_usd": 0,
            "price_yearly_usd": 0,
            "yearly_discount_pct": 0,
            "trial_days": 0,
            "support_level": "community",
            "stripe_price_monthly": None,
            "stripe_price_yearly": None,
            "limits": {
                "ai_messages_per_month": 50,
                "conversations": 5,
                "active_modules": 1,
                "api_calls_per_day": 0,
                "storage_gb": 1,
            },
            "features": ["1 AI module", "50 messages/month", "Community support"],
            "features_enabled": {
                "api_access": False,
                "white_label": False,
                "priority_support": False,
                "advanced_analytics": False,
                "custom_modules": False,
                "automation": False,
                "team_seats": False,
                "data_export": False,
                "overage_allowed": False,
                "early_access": False,
            },
        },
        "pro": {
            "name": "Pro",
            "price_monthly_usd": 29,
            "price_yearly_usd": 290,
            "yearly_discount_pct": 17,
            "trial_days": 14,
            "support_level": "priority",
            "stripe_price_monthly": settings.STRIPE_PRICE_PRO_MONTHLY_ID or None,
            "stripe_price_yearly": settings.STRIPE_PRICE_PRO_YEARLY_ID or None,
            "limits": {
                "ai_messages_per_month": 1000,
                "conversations": 100,
                "active_modules": 5,
                "api_calls_per_day": 500,
                "storage_gb": 10,
            },
            "features": ["5 AI modules", "1,000 messages/month", "Priority support", "API access", "Data export"],
            "features_enabled": {
                "api_access": True,
                "white_label": False,
                "priority_support": True,
                "advanced_analytics": True,
                "custom_modules": False,
                "automation": True,
                "team_seats": False,
                "data_export": True,
                "overage_allowed": True,
                "early_access": False,
            },
        },
        "business": {
            "name": "Business",
            "price_monthly_usd": 99,
            "price_yearly_usd": 990,
            "yearly_discount_pct": 17,
            "trial_days": 14,
            "support_level": "dedicated",
            "stripe_price_monthly": settings.STRIPE_PRICE_BUSINESS_MONTHLY_ID or None,
            "stripe_price_yearly": settings.STRIPE_PRICE_BUSINESS_YEARLY_ID or None,
            "limits": {
                "ai_messages_per_month": -1,
                "conversations": -1,
                "active_modules": 10,
                "api_calls_per_day": -1,
                "storage_gb": 100,
            },
            "features": [
                "All 10 AI modules",
                "Unlimited messages",
                "Dedicated support",
                "White-label option",
                "API access",
                "Team seats",
                "Early access features",
            ],
            "features_enabled": {
                "api_access": True,
                "white_label": True,
                "priority_support": True,
                "advanced_analytics": True,
                "custom_modules": True,
                "automation": True,
                "team_seats": True,
                "data_export": True,
                "overage_allowed": True,
                "early_access": True,
            },
        },
    }


PLANS_CONFIG: dict[str, dict] = _build_plans()

# ─── Add-on packs — server-side only, never from client ──────────────────────
ADDONS_CONFIG: dict[str, dict] = {
    "api_calls_500": {
        "name": "API Calls Pack — 500",
        "description": "+500 API calls for the current month",
        "price_usd": 5,
        "stripe_price_id": settings.STRIPE_PRICE_ADDON_API_PACK or None,
        "type": "one_time",
        "grants": {"api_calls_extra": 500},
    },
    "storage_10gb": {
        "name": "Storage Pack — 10 GB",
        "description": "+10 GB storage add-on",
        "price_usd": 5,
        "stripe_price_id": settings.STRIPE_PRICE_ADDON_STORAGE_10GB or None,
        "type": "one_time",
        "grants": {"storage_gb_extra": 10},
    },
    "credits_50": {
        "name": "Credit Pack — 50 credits",
        "description": "50 overage credits (1 credit = 1 extra message beyond plan limit)",
        "price_usd": 4,
        "stripe_price_id": settings.STRIPE_PRICE_CREDITS_PACK or None,
        "type": "one_time",
        "grants": {"credits": 50},
    },
}

# Gamification milestones — progression system for user engagement / lock-in
MILESTONES: list[dict] = [
    {"key": "first_message", "label": "First AI message sent", "threshold": 1, "icon": "🤖"},
    {"key": "ten_messages", "label": "10 messages sent", "threshold": 10, "icon": "🔥"},
    {"key": "fifty_messages", "label": "50 messages sent", "threshold": 50, "icon": "⚡"},
    {"key": "hundred_messages", "label": "100 messages — Power user", "threshold": 100, "icon": "🏆"},
    {"key": "pro_subscriber", "label": "Subscribed to Pro", "threshold": 0, "icon": "💎", "plan": "pro"},
    {"key": "business_subscriber", "label": "Subscribed to Business", "threshold": 0, "icon": "👑", "plan": "business"},
]

# Reverse map: stripe_price_id → plan slug (built once at import)
_PRICE_TO_PLAN: dict[str, str] = {
    price_id: slug
    for slug, cfg in PLANS_CONFIG.items()
    for key in ("stripe_price_monthly", "stripe_price_yearly")
    if (price_id := cfg.get(key))
}


def price_id_to_plan(price_id: str | None) -> str:
    if not price_id:
        return "free"
    return _PRICE_TO_PLAN.get(price_id, "pro")


# ─── Feature gating ───────────────────────────────────────────────────────────

# Maps each feature flag to the minimum plan required (in upgrade order)
_PLAN_ORDER = ["free", "pro", "business"]

def has_feature(user_plan: str, feature: str) -> bool:
    """
    Returns True if the user's plan includes the given feature flag.
    Server-side only — never trust client-side claims.
    """
    plan_cfg = PLANS_CONFIG.get(user_plan if user_plan in PLANS_CONFIG else "free")
    return plan_cfg["features_enabled"].get(feature, False)


def get_upsell_suggestion(user_plan: str, usage: dict | None = None) -> dict | None:
    """
    Returns a contextual upsell suggestion based on current plan and usage.
    Returns None if already on highest tier.
    """
    if user_plan == "business":
        return None

    next_plan = "pro" if user_plan == "free" else "business"
    next_cfg = PLANS_CONFIG[next_plan]
    current_cfg = PLANS_CONFIG.get(user_plan, PLANS_CONFIG["free"])

    # Detect usage-based trigger
    trigger = None
    if usage:
        limit = current_cfg["limits"]["ai_messages_per_month"]
        count = usage.get("messages_count", 0)
        if limit > 0 and count >= limit * 0.8:
            trigger = "usage_limit_80pct"
        elif limit > 0 and count >= limit:
            trigger = "usage_limit_reached"

    # Compute savings on yearly
    monthly_price = next_cfg["price_monthly_usd"]
    yearly_price = next_cfg["price_yearly_usd"]
    yearly_savings = (monthly_price * 12) - yearly_price

    return {
        "next_plan": next_plan,
        "next_plan_name": next_cfg["name"],
        "price_monthly_usd": monthly_price,
        "price_yearly_usd": yearly_price,
        "yearly_discount_pct": next_cfg["yearly_discount_pct"],
        "yearly_savings_usd": yearly_savings,
        "trigger": trigger,
        "headline": (
            f"Passez à {next_cfg['name']} — {next_cfg['yearly_discount_pct']}% de réduction annuelle"
            if next_cfg["yearly_discount_pct"] > 0
            else f"Passez à {next_cfg['name']}"
        ),
        "new_features": [
            f for f, enabled in next_cfg["features_enabled"].items()
            if enabled and not current_cfg["features_enabled"].get(f, False)
        ],
    }


# ─── Stripe customer ──────────────────────────────────────────────────────────

async def get_or_create_stripe_customer(user: User, db: AsyncSession) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        name=user.full_name,
        metadata={"user_id": str(user.id), "app": settings.APP_NAME},
    )
    user.stripe_customer_id = customer.id
    db.add(user)
    await db.commit()
    logger.info(f"[billing] Created Stripe customer {customer.id} for user {user.id}")
    return customer.id


# ─── Subscription sync ────────────────────────────────────────────────────────

async def get_active_subscription(user_id: uuid.UUID, db: AsyncSession) -> Subscription | None:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def sync_subscription_from_stripe(
    stripe_sub: dict[str, Any], db: AsyncSession
) -> Subscription | None:
    """
    Upsert Subscription row from Stripe subscription object.
    Idempotent — safe to call multiple times with same data.
    Syncs User.plan to match subscription status.
    """
    stripe_sub_id = stripe_sub["id"]
    stripe_customer_id = stripe_sub["customer"]

    result = await db.execute(
        select(User).where(User.stripe_customer_id == stripe_customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        logger.warning(f"[billing] No user for Stripe customer {stripe_customer_id}")
        return None

    price_id = None
    items = stripe_sub.get("items", {}).get("data", [])
    if items:
        price_id = items[0]["price"]["id"]
    plan = price_id_to_plan(price_id)

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        sub = Subscription(user_id=user.id)
        db.add(sub)

    sub.stripe_subscription_id = stripe_sub_id
    sub.stripe_price_id = price_id
    sub.plan = plan
    sub.status = stripe_sub["status"]
    sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)

    if stripe_sub.get("current_period_start"):
        sub.current_period_start = datetime.fromtimestamp(
            stripe_sub["current_period_start"], tz=timezone.utc
        )
    if stripe_sub.get("current_period_end"):
        sub.current_period_end = datetime.fromtimestamp(
            stripe_sub["current_period_end"], tz=timezone.utc
        )

    # Keep User.plan in sync
    if stripe_sub["status"] == "active":
        user.plan = plan
    elif stripe_sub["status"] in ("canceled", "unpaid", "incomplete_expired"):
        user.plan = "free"
    db.add(user)

    await _write_audit(
        db, user.id,
        action=f"subscription_{stripe_sub['status']}",
        detail=f"plan={plan} stripe_sub={stripe_sub_id}",
    )

    await db.commit()
    await db.refresh(sub)
    logger.info(f"[billing] Synced sub {stripe_sub_id} plan={plan} status={stripe_sub['status']}")
    return sub


async def handle_checkout_completed(session: dict[str, Any], db: AsyncSession) -> None:
    """
    Handle checkout.session.completed:
    - Links Stripe customer to our user (first purchase)
    - If mode=payment + type=credits → increments user.credits immediately
    """
    customer_id = session.get("customer")
    user_id_str = session.get("client_reference_id")
    if not customer_id or not user_id_str:
        logger.warning("[billing] checkout.session.completed missing customer or client_reference_id")
        return

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        logger.error(f"[billing] Invalid client_reference_id: {user_id_str}")
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.error(f"[billing] No user for id={user_id_str}")
        return

    if not user.stripe_customer_id:
        user.stripe_customer_id = customer_id
        db.add(user)
        logger.info(f"[billing] Linked customer {customer_id} to user {user_id}")

    # Credit pack one-time purchase
    metadata = session.get("metadata") or {}
    if session.get("mode") == "payment" and metadata.get("type") == "credits":
        try:
            credits_to_add = int(metadata.get("credits", 0))
        except (ValueError, TypeError):
            credits_to_add = 0
        if credits_to_add > 0:
            user.credits = (user.credits or 0) + credits_to_add
            db.add(user)
            logger.info(f"[billing] Added {credits_to_add} credits to user {user_id} → total={user.credits}")
            await _write_audit(db, user_id, "credits_purchased", f"+{credits_to_add} credits via Stripe")

    await db.commit()


async def _write_audit(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    action: str,
    detail: str | None = None,
) -> None:
    """Insert a row in audit_logs for billing events."""
    from api.models.audit import AuditLog  # local import avoids circular deps
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource="billing",
        status="success",
        detail=detail,
    )
    db.add(log)
    # Flushed as part of the caller's commit — no extra commit here


# ─── Webhook idempotency ──────────────────────────────────────────────────────

async def is_event_processed(event_id: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
    )
    return result.scalar_one_or_none() is not None


async def mark_event(
    event_id: str,
    event_type: str,
    status: str,
    error: str | None,
    db: AsyncSession,
) -> None:
    we = WebhookEvent(
        stripe_event_id=event_id,
        event_type=event_type,
        processed_at=datetime.now(timezone.utc),
        status=status,
        error=error,
    )
    db.add(we)
    await db.commit()


# ─── Entitlement computation — always from DB, never from client ──────────────

def compute_entitlements(user: User, sub: Subscription | None, usage: dict | None = None) -> dict:
    plan_key = user.plan if user.plan in PLANS_CONFIG else "free"

    # Degrade to free if subscription is in bad standing
    if sub and sub.status in ("past_due", "canceled", "unpaid", "incomplete_expired"):
        plan_key = "free"

    plan_cfg = PLANS_CONFIG[plan_key]
    now = datetime.now(timezone.utc)

    is_sub_active = (
        sub is not None
        and sub.status == "active"
        and (sub.current_period_end is None or sub.current_period_end > now)
    )
    effective_status = "active" if (plan_key == "free" or is_sub_active) else (
        sub.status if sub else "inactive"
    )

    return {
        "plan": plan_key,
        "status": effective_status,
        "limits": plan_cfg["limits"],
        "features": plan_cfg["features"],
        "features_enabled": plan_cfg["features_enabled"],
        "credits": user.credits,
        "subscription": {
            "id": sub.stripe_subscription_id if sub else None,
            "current_period_end": (
                sub.current_period_end.isoformat() if sub and sub.current_period_end else None
            ),
            "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
            "billing_interval": getattr(sub, "billing_interval", None) if sub else None,
        },
        "upsell": get_upsell_suggestion(plan_key, usage),
    }
