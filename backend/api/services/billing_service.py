# -*- coding: utf-8 -*-
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

import asyncio
import logging
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import stripe
from sqlalchemy import select, update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models.subscription import Subscription
from api.models.user import User
from api.models.webhook_event import WebhookEvent
from api.services.module_registry import (
    MODULE_REGISTRY,
    PUBLIC_MONETIZATION_CATALOG,
    canonicalize_module_slug,
    get_module_lookup_slugs,
)

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = "2026-04-22.dahlia"

# ─── Plan configuration — server-side ONLY, never from client ────────────────
def _build_plans() -> dict[str, dict]:
    plans = deepcopy(PUBLIC_MONETIZATION_CATALOG["plans"])
    stripe_ids = {
        "free": (None, None),
        "pro": (
            settings.STRIPE_PRICE_PRO_MONTHLY_ID or None,
            settings.STRIPE_PRICE_PRO_YEARLY_ID or None,
        ),
        "business": (
            settings.STRIPE_PRICE_BUSINESS_MONTHLY_ID or None,
            settings.STRIPE_PRICE_BUSINESS_YEARLY_ID or None,
        ),
    }
    for slug, (monthly_id, yearly_id) in stripe_ids.items():
        plans[slug]["stripe_price_monthly"] = monthly_id
        plans[slug]["stripe_price_yearly"] = yearly_id
    return plans


PLANS_CONFIG: dict[str, dict] = _build_plans()

# ─── Add-on packs — server-side only, never from client ──────────────────────
def _build_addons() -> dict[str, dict]:
    addons = deepcopy(PUBLIC_MONETIZATION_CATALOG["addons"])
    stripe_ids = {
        "api_calls_500": settings.STRIPE_PRICE_ADDON_API_PACK or None,
        "storage_10gb": settings.STRIPE_PRICE_ADDON_STORAGE_10GB or None,
        "credits_50": settings.STRIPE_PRICE_CREDITS_PACK or None,
    }
    for slug, stripe_price_id in stripe_ids.items():
        addons[slug]["stripe_price_id"] = stripe_price_id
    return addons


ADDONS_CONFIG: dict[str, dict] = _build_addons()

# ─── Per-module à-la-carte pricing ────────────────────────────────────────────
def _build_modules() -> dict[str, dict]:
    modules = deepcopy(MODULE_REGISTRY)
    stripe_ids = {
        "operator": settings.STRIPE_PRICE_MODULE_OPERATOR or None,
        "content": settings.STRIPE_PRICE_MODULE_CONTENT or None,
        "micro_saas": settings.STRIPE_PRICE_MODULE_MICRO_SAAS or None,
        "ghost": settings.STRIPE_PRICE_MODULE_GHOST or None,
        "decision": settings.STRIPE_PRICE_MODULE_DECISION or None,
        "knowledge": settings.STRIPE_PRICE_MODULE_KNOWLEDGE or None,
        "leverage": settings.STRIPE_PRICE_MODULE_LEVERAGE or None,
        "reverse": settings.STRIPE_PRICE_MODULE_REVERSE or None,
        "offer": settings.STRIPE_PRICE_MODULE_OFFER or None,
        "execution": settings.STRIPE_PRICE_MODULE_EXECUTION or None,
    }
    for slug, cfg in modules.items():
        cfg["slug"] = slug
        cfg["stripe_price_id"] = stripe_ids[slug]
        cfg["included_in_plans"] = [
            plan_slug
            for plan_slug, plan_cfg in PUBLIC_MONETIZATION_CATALOG["plans"].items()
            if slug in plan_cfg.get("included_modules", [])
        ]
    return modules


MODULES_CONFIG: dict[str, dict] = _build_modules()

# Gamification milestones -- progression system for user engagement / lock-in
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

_PRICE_TO_MODULE: dict[str, str] = {
    cfg["stripe_price_id"]: slug
    for slug, cfg in MODULES_CONFIG.items()
    if cfg.get("stripe_price_id")
}


def price_id_to_plan(price_id: str | None) -> str | None:
    if not price_id:
        return None
    return _PRICE_TO_PLAN.get(price_id)


def price_id_to_module(price_id: str | None) -> str | None:
    if not price_id:
        return None
    return _PRICE_TO_MODULE.get(price_id)


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

    metadata = stripe_sub.get("metadata") or {}
    price_id = None
    items = stripe_sub.get("items", {}).get("data", [])
    if items:
        price_id = items[0]["price"]["id"]

    module_slug = (
        canonicalize_module_slug(metadata.get("module"))
        if metadata.get("type") == "module"
        else price_id_to_module(price_id)
    )
    if module_slug:
        await sync_module_subscription_from_stripe(stripe_sub, module_slug, db)
        return None

    plan = price_id_to_plan(price_id)
    if not plan:
        metadata_plan = metadata.get("plan")
        if metadata_plan in PLANS_CONFIG:
            plan = metadata_plan
        else:
            logger.error(
                "[billing] Unknown Stripe price id %s for subscription %s — refusing unsafe plan sync",
                price_id,
                stripe_sub_id,
            )
            await _write_audit(
                db,
                user.id,
                action="subscription_sync_skipped_unknown_price",
                detail=f"stripe_sub={stripe_sub_id} price_id={price_id}",
            )
            await db.commit()
            return None

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

    if stripe_sub.get("trial_end"):
        sub.trial_end = datetime.fromtimestamp(stripe_sub["trial_end"], tz=timezone.utc)

    # Sync billing interval from price recurring
    if items:
        interval = items[0].get("price", {}).get("recurring", {}).get("interval")
        if interval:
            sub.billing_interval = "yearly" if interval == "year" else "monthly"

    old_plan = user.plan
    # Keep User.plan in sync — trialing counts as active for feature access
    if stripe_sub["status"] in ("active", "trialing"):
        user.plan = plan
    elif stripe_sub["status"] in ("past_due",):
        # past_due: keep plan but entitlements degrade (handled in compute_entitlements)
        pass
    elif stripe_sub["status"] in ("canceled", "unpaid", "incomplete_expired"):
        user.plan = "free"
    db.add(user)

    await _write_audit(
        db, user.id,
        action=f"subscription_{stripe_sub['status']}",
        detail=f"plan={plan} stripe_sub={stripe_sub_id}",
    )
    if user.plan != old_plan:
        await _write_audit(
            db,
            user.id,
            action="plan_changed_via_webhook",
            detail=f"{old_plan}->{user.plan} stripe_sub={stripe_sub_id} status={stripe_sub['status']}",
        )

    await db.commit()
    await db.refresh(sub)
    logger.info(f"[billing] Synced sub {stripe_sub_id} plan={plan} status={stripe_sub['status']}")
    return sub


async def sync_module_subscription_from_stripe(
    stripe_sub: dict[str, Any],
    module_slug: str,
    db: AsyncSession,
) -> None:
    """Upsert module access from a Stripe subscription without mutating User.plan."""
    from api.models.user_module import UserModule

    raw_module_identifier = module_slug
    module_slug = canonicalize_module_slug(module_slug)
    if not module_slug:
        logger.warning(
            "[billing] Unknown module identifier %s for Stripe module subscription %s",
            raw_module_identifier,
            stripe_sub.get("id"),
        )
        return

    stripe_sub_id = stripe_sub["id"]
    stripe_customer_id = stripe_sub["customer"]
    lookup_slugs = get_module_lookup_slugs(module_slug)

    result = await db.execute(
        select(User).where(User.stripe_customer_id == stripe_customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        logger.warning(
            "[billing] No user for Stripe module subscription customer %s",
            stripe_customer_id,
        )
        return

    result = await db.execute(
        select(UserModule).where(
            UserModule.user_id == user.id,
            UserModule.module_slug.in_(lookup_slugs),
        )
    )
    module_access = result.scalar_one_or_none()
    if module_access is None:
        from api.models.user_module import UserModule as UserModuleModel

        module_access = UserModuleModel(user_id=user.id, module_slug=module_slug)
        db.add(module_access)
    else:
        module_access.module_slug = module_slug

    module_access.stripe_subscription_id = stripe_sub_id
    module_access.stripe_customer_id = stripe_customer_id
    module_access.status = stripe_sub["status"]
    module_access.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)
    if stripe_sub.get("current_period_end"):
        module_access.expires_at = datetime.fromtimestamp(
            stripe_sub["current_period_end"], tz=timezone.utc
        )
    else:
        module_access.expires_at = None

    await _write_audit(
        db,
        user.id,
        action=f"module_subscription_{stripe_sub['status']}",
        detail=f"module={module_slug} stripe_sub={stripe_sub_id}",
    )
    await db.commit()
    logger.info(
        "[billing] Synced module subscription %s module=%s status=%s",
        stripe_sub_id,
        module_slug,
        stripe_sub["status"],
    )


async def resync_user_subscription_from_stripe(user_id: uuid.UUID, db: AsyncSession) -> dict[str, Any]:
    """
    Force-fetch the latest Stripe customer/subscription state and sync it locally.
    Safe for admin recovery when webhook delivery or previous processing drifted.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    customer_id = user.stripe_customer_id
    if not customer_id:
        customers = stripe.Customer.list(email=user.email, limit=10)
        for customer in customers.data:
            if customer.get("metadata", {}).get("user_id") == str(user.id) or customer.get("email") == user.email:
                customer_id = customer["id"]
                user.stripe_customer_id = customer_id
                db.add(user)
                break
        await db.commit()

    if not customer_id:
        await _write_audit(
            db,
            user.id,
            action="billing_resync_no_customer",
            detail="No Stripe customer found during admin resync",
        )
        await db.commit()
        return {"status": "no_customer", "user_id": str(user.id)}

    subs = stripe.Subscription.list(customer=customer_id, status="all", limit=20)
    if not subs.data:
        await _write_audit(
            db,
            user.id,
            action="billing_resync_no_subscription",
            detail=f"customer={customer_id}",
        )
        await db.commit()
        return {"status": "no_subscription", "user_id": str(user.id), "customer_id": customer_id}

    latest_sub = sorted(
        subs.data,
        key=lambda sub: (
            sub.get("current_period_end") or 0,
            sub.get("created") or 0,
        ),
        reverse=True,
    )[0]
    await sync_subscription_from_stripe(latest_sub, db)
    return {
        "status": "resynced",
        "user_id": str(user.id),
        "customer_id": customer_id,
        "stripe_subscription_id": latest_sub["id"],
        "subscription_status": latest_sub.get("status"),
    }


async def activate_user_module(
    user_id: str,
    module_slug: str,
    stripe_subscription_id: str | None,
    stripe_customer_id: str | None,
    db: AsyncSession,
) -> None:
    """
    Grant a user access to a specific module after successful payment.
    Uses upsert pattern — safe to call multiple times (idempotent).
    """
    import uuid as _uuid
    from api.models.user_module import UserModule
    from sqlalchemy import select as _select

    module_slug = canonicalize_module_slug(module_slug)
    if not module_slug:
        raise ValueError("Unknown module slug")

    lookup_slugs = get_module_lookup_slugs(module_slug)

    existing = await db.execute(
        _select(UserModule).where(
            UserModule.user_id == _uuid.UUID(str(user_id)),
            UserModule.module_slug.in_(lookup_slugs),
        )
    )
    row = existing.scalar_one_or_none()

    if row:
        # Update existing row — reactivate if cancelled
        row.module_slug = module_slug
        row.status = "active"
        row.stripe_subscription_id = stripe_subscription_id or row.stripe_subscription_id
        row.stripe_customer_id = stripe_customer_id or row.stripe_customer_id
        row.expires_at = None
        row.cancel_at_period_end = False
    else:
        row = UserModule(
            user_id=_uuid.UUID(str(user_id)),
            module_slug=module_slug,
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer_id,
            status="active",
        )
        db.add(row)

    await db.commit()
    logger.info(f"[billing] Module '{module_slug}' activated for user {user_id}")


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
        session_id = session.get("id")
        if not session_id:
            logger.error("[billing] checkout.session.completed missing session id — cannot safely credit")
            return
        if credits_to_add > 0:
            from api.services.credit_service import add_credits
            idempotency_key = f"stripe_checkout_{session_id}_{credits_to_add}"
            await add_credits(
                user_id=user_id,
                amount=credits_to_add,
                source="stripe_checkout",
                db=db,
                idempotency_key=idempotency_key,
                note=f"Credit pack purchased via Stripe checkout {session.get('id', '')}",
            )
            logger.info(f"[billing] Added {credits_to_add} credits to user {user_id} via ledger")
            await _write_audit(db, user_id, "credits_purchased", f"+{credits_to_add} credits via Stripe")

    # Module à-la-carte purchase
    checkout_type = metadata.get("type", "")
    if checkout_type == "module":
        module_slug = canonicalize_module_slug(metadata.get("module"))
        if module_slug and user_id_str:
            await activate_user_module(
                user_id=user_id_str,
                module_slug=module_slug,
                stripe_subscription_id=session.get("subscription"),
                stripe_customer_id=customer_id,
                db=db,
            )
            try:
                from prometheus_client import Counter
                Counter(
                    "kt_module_purchases_total",
                    "Module subscription purchases completed",
                    ["module"],
                ).labels(module=module_slug).inc()
            except Exception:
                pass

    await db.commit()


async def _get_user_by_stripe_customer_id(
    stripe_customer_id: str | None,
    db: AsyncSession,
) -> User | None:
    if not stripe_customer_id:
        return None
    result = await db.execute(select(User).where(User.stripe_customer_id == stripe_customer_id))
    return result.scalar_one_or_none()


def _queue_telegram_stripe_alert(
    event_type: str,
    data: dict[str, Any],
    *,
    status: str,
    user_email: str | None = None,
) -> None:
    from api.services.telegram_service import send_stripe_event_alert

    asyncio.create_task(
        send_stripe_event_alert(
            event_type,
            data,
            status=status,
            user_email=user_email,
        )
    )


async def process_stripe_event(
    event_type: str,
    data: dict[str, Any],
    db: AsyncSession,
) -> str:
    """Apply a Stripe event to local billing state and return the resulting status."""
    if event_type == "checkout.session.completed":
        await handle_checkout_completed(data, db)
        user = await _get_user_by_stripe_customer_id(data.get("customer"), db)
        _queue_telegram_stripe_alert(
            event_type,
            data,
            status="processed",
            user_email=user.email if user else None,
        )
        return "processed"

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        await sync_subscription_from_stripe(data, db)
        user = await _get_user_by_stripe_customer_id(data.get("customer"), db)
        await _write_audit(
            db,
            user.id if user else None,
            event_type.replace(".", "_"),
            (
                f"subscription={data.get('id')} "
                f"status={data.get('status')} "
                f"customer={data.get('customer')}"
            ),
        )

        if event_type == "customer.subscription.created":
            try:
                from api.services.email_service import send_billing_confirmation

                if user:
                    plan = data.get("metadata", {}).get("plan", "Pro")
                    items = data.get("items", {}).get("data", [])
                    amount = items[0]["price"]["unit_amount"] / 100 if items else 0.0
                    asyncio.create_task(
                        send_billing_confirmation(user.email, plan, amount)
                    )
            except Exception as exc:
                logger.warning("[webhook] Could not queue billing email: %s", exc)

        if event_type == "customer.subscription.deleted":
            try:
                from api.services.email_service import send_subscription_cancelled

                if user:
                    plan_name = (
                        data.get("metadata", {}).get("plan")
                        or (user.plan or "free").capitalize()
                    )
                    asyncio.create_task(
                        send_subscription_cancelled(user.email, user.full_name or "", plan_name)
                    )
            except Exception as exc:
                logger.warning("[webhook] Could not queue cancellation email: %s", exc)

        _queue_telegram_stripe_alert(
            event_type,
            data,
            status="processed",
            user_email=user.email if user else None,
        )
        return "processed"

    if event_type == "invoice.payment_succeeded":
        user = await _get_user_by_stripe_customer_id(data.get("customer"), db)
        await _write_audit(
            db,
            user.id if user else None,
            "invoice_payment_succeeded",
            f"invoice={data.get('id')} amount_paid={data.get('amount_paid')} customer={data.get('customer')}",
        )
        logger.info(
            "[webhook] Payment succeeded for customer %s amount=%s invoice=%s",
            data.get("customer"),
            data.get("amount_paid"),
            data.get("id"),
        )
        _queue_telegram_stripe_alert(
            event_type,
            data,
            status="processed",
            user_email=user.email if user else None,
        )
        return "processed"

    if event_type == "invoice.payment_failed":
        user = await _get_user_by_stripe_customer_id(data.get("customer"), db)
        await _write_audit(
            db,
            user.id if user else None,
            "invoice_payment_failed",
            (
                f"invoice={data.get('id')} attempt_count={data.get('attempt_count')} "
                f"customer={data.get('customer')}"
            ),
        )
        logger.warning(
            "[webhook] Payment FAILED for customer %s attempt=%s invoice=%s",
            data.get("customer"),
            data.get("attempt_count"),
            data.get("id"),
        )
        try:
            from api.services.subscription_state_machine import handle_payment_failed

            if user:
                result = await db.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .order_by(Subscription.created_at.desc())
                    .limit(1)
                )
                sub = result.scalar_one_or_none()
                await handle_payment_failed(user, sub, db)
        except Exception as exc:
            logger.warning("[webhook] Could not handle payment-failed: %s", exc)
        _queue_telegram_stripe_alert(
            event_type,
            data,
            status="processed",
            user_email=user.email if user else None,
        )
        return "processed"

    if event_type == "customer.subscription.trial_will_end":
        user = await _get_user_by_stripe_customer_id(data.get("customer"), db)
        await _write_audit(
            db,
            user.id if user else None,
            "customer_subscription_trial_will_end",
            f"subscription={data.get('id')} customer={data.get('customer')} trial_end={data.get('trial_end')}",
        )
        logger.info("[webhook] Trial ending soon for customer %s", data.get("customer"))
        try:
            from api.services.subscription_state_machine import handle_trial_will_end

            if user:
                result = await db.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .order_by(Subscription.created_at.desc())
                    .limit(1)
                )
                sub = result.scalar_one_or_none()
                trial_end_ts = data.get("trial_end")
                days_left = 3
                if trial_end_ts:
                    trial_end_dt = datetime.fromtimestamp(trial_end_ts, tz=timezone.utc)
                    delta = trial_end_dt - datetime.now(timezone.utc)
                    days_left = max(1, delta.days)
                if sub:
                    await handle_trial_will_end(user, sub, days_left, db)
        except Exception as exc:
            logger.warning("[webhook] Could not handle trial_will_end: %s", exc)
        _queue_telegram_stripe_alert(
            event_type,
            data,
            status="processed",
            user_email=user.email if user else None,
        )
        return "processed"

    logger.debug("[webhook] Unhandled event type: %s", event_type)
    return "ignored"


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

async def claim_webhook_event(event_id: str, event_type: str, db: AsyncSession) -> bool:
    """
    Atomically claim a webhook event for processing.
    Returns True if claimed (first time). Returns False if already claimed (duplicate).

    Race-safe: uses the DB UNIQUE constraint on stripe_event_id as the
    synchronization mechanism. Two concurrent requests for the same event_id
    will both attempt the INSERT; only one succeeds. The loser gets
    IntegrityError → returns False → caller returns HTTP 200 immediately.
    """
    try:
        we = WebhookEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            processed_at=datetime.now(timezone.utc),
            status="processing",
            error=None,
        )
        db.add(we)
        await db.commit()
        return True
    except IntegrityError:
        await db.rollback()
        logger.info("[webhook] Duplicate event %s — already claimed", event_id)
        return False


async def update_webhook_status(
    event_id: str, status: str, error: str | None, db: AsyncSession
) -> None:
    """Update the status of a previously claimed webhook event. Called after processing."""
    await db.execute(
        sql_update(WebhookEvent)
        .where(WebhookEvent.stripe_event_id == event_id)
        .values(
            status=status,
            error=error,
            processed_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


async def get_webhook_event(event_id: str, db: AsyncSession) -> WebhookEvent | None:
    """Fetch a stored webhook event by Stripe event id."""
    result = await db.execute(
        select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
    )
    return result.scalar_one_or_none()


# ── Legacy aliases — kept for backward compat with any external callers ───────
async def is_event_processed(event_id: str, db: AsyncSession) -> bool:
    """Deprecated: use claim_webhook_event instead (not race-safe)."""
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
    """Deprecated: use update_webhook_status instead. Updates existing row."""
    try:
        await db.execute(
            sql_update(WebhookEvent)
            .where(WebhookEvent.stripe_event_id == event_id)
            .values(status=status, error=error)
        )
        await db.commit()
    except Exception:
        # Row may not exist if called outside claim_webhook_event flow
        await db.rollback()


# ─── Entitlement computation — always from DB, never from client ──────────────

def compute_entitlements(user: User, sub: Subscription | None, usage: dict | None = None) -> dict:
    plan_key = user.plan if user.plan in PLANS_CONFIG else "free"

    # Degrade to free if subscription is in bad standing
    if sub and sub.status in ("canceled", "unpaid", "incomplete_expired"):
        plan_key = "free"
    # past_due: keep current plan for grace period (Stripe retries automatically)

    plan_cfg = PLANS_CONFIG[plan_key]
    now = datetime.now(timezone.utc)

    is_sub_active = (
        sub is not None
        and sub.status in ("active", "trialing", "past_due")
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
