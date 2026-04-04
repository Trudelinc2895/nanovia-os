"""
backend/api/routers/billing.py

Production-grade Stripe billing:
  GET  /plans                  — public plan catalogue
  GET  /subscription           — current subscription (auth)
  GET  /entitlements           — computed access rights (auth)
  POST /checkout-session       — create Stripe checkout (auth)
  POST /portal-session         — open Stripe billing portal (auth)
  POST /credits/purchase       — buy credit pack (auth)
  POST /webhook                — Stripe webhook, sig-verified, idempotent

SECURITY:
  - Plan/price resolved server-side from PLANS_CONFIG only (never client)
  - Webhook: raw body signature verification on every call
  - Auth required on all user-facing endpoints
  - client_reference_id links checkout session to authenticated user
"""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.core.deps import CurrentUser, DB
from api.schemas.billing import (
    AddonCheckoutRequest,
    AddonCheckoutResponse,
    AddonPublic,
    CheckoutRequest,
    CheckoutResponse,
    CreditPurchaseRequest,
    CreditPurchaseResponse,
    EntitlementsResponse,
    ModuleCheckoutRequest,
    ModulePublic,
    PlanPublic,
    PortalResponse,
    UsageResponse,
)
from api.services.billing_service import (
    ADDONS_CONFIG,
    MODULES_CONFIG,
    PLANS_CONFIG,
    compute_entitlements,
    get_active_subscription,
    get_or_create_stripe_customer,
    get_upsell_suggestion,
    handle_checkout_completed,
    has_feature,
    is_event_processed,
    mark_event,
    sync_subscription_from_stripe,
)
from api.services.email_service import send_billing_confirmation, send_payment_failed
from api.services.usage_service import get_monthly_usage

logger = logging.getLogger(__name__)
router = APIRouter()
stripe.api_key = settings.STRIPE_SECRET_KEY


# ─── Public ───────────────────────────────────────────────────────────────────

@router.get("/plans", response_model=list[PlanPublic])
async def list_plans() -> list[PlanPublic]:
    """Return all available plans with pricing, limits, and feature gates."""
    return [
        PlanPublic(
            slug=slug,
            name=cfg["name"],
            price_monthly_usd=cfg["price_monthly_usd"],
            price_yearly_usd=cfg["price_yearly_usd"],
            yearly_discount_pct=cfg["yearly_discount_pct"],
            trial_days=cfg["trial_days"],
            support_level=cfg["support_level"],
            limits=cfg["limits"],
            features=cfg["features"],
            features_enabled=cfg["features_enabled"],
        )
        for slug, cfg in PLANS_CONFIG.items()
    ]


@router.get("/modules", response_model=list[ModulePublic])
async def list_modules() -> list[ModulePublic]:
    """Return all available à-la-carte modules with pricing."""
    return [
        ModulePublic(
            slug=cfg["slug"],
            name=cfg["name"],
            price_usd=cfg["price_usd"],
            description=cfg["description"],
            available=bool(cfg.get("stripe_price_id")),
        )
        for cfg in MODULES_CONFIG.values()
    ]


@router.get("/my-modules")
async def get_my_modules(current_user: CurrentUser, db: DB):
    """
    Return all modules the user has access to, with their source:
    - "plan": included in current plan
    - "purchased": individually purchased
    - "locked": not available on this plan / not purchased
    """
    from api.models.user_module import UserModule as _UserModule
    from sqlalchemy import select as _select

    # Get individually purchased modules
    result = await db.execute(
        _select(_UserModule).where(
            _UserModule.user_id == current_user.id,
            _UserModule.status.in_(["active", "trialing"]),
        )
    )
    purchased_slugs = {row.module_slug for row in result.scalars().all()}

    # Define which modules are included in each plan
    PLAN_INCLUDED_MODULES: dict[str, set[str]] = {
        "free": {"operator"},
        "pro": {"operator", "content", "decision", "knowledge", "leverage"},
        "business": set(MODULES_CONFIG.keys()),  # all 10
    }
    plan_modules = PLAN_INCLUDED_MODULES.get(current_user.plan, set())

    modules_status = []
    for slug, cfg in MODULES_CONFIG.items():
        if slug in purchased_slugs:
            source = "purchased"
            access = True
        elif slug in plan_modules:
            source = "plan"
            access = True
        else:
            source = "locked"
            access = False

        modules_status.append({
            "slug": slug,
            "name": cfg["name"],
            "price_usd": cfg["price_usd"],
            "description": cfg["description"],
            "access": access,
            "source": source,
            "stripe_price_id_available": bool(cfg.get("stripe_price_id")),
        })

    return {
        "plan": current_user.plan,
        "modules": modules_status,
    }


# ─── Authenticated billing endpoints ─────────────────────────────────────────

@router.get("/subscription")
async def get_subscription(current_user: CurrentUser, db: DB):
    """Return user's current subscription details."""
    sub = await get_active_subscription(current_user.id, db)
    if not sub:
        return {
            "plan": current_user.plan,
            "status": "free",
            "subscription_id": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
        }
    return {
        "plan": sub.plan,
        "status": sub.status,
        "subscription_id": sub.stripe_subscription_id,
        "current_period_end": (
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


@router.get("/entitlements", response_model=EntitlementsResponse)
async def get_entitlements(current_user: CurrentUser, db: DB):
    """
    Return what the authenticated user can access.
    Computed server-side from DB state — never trust client plan claims.
    Includes credits, feature gates, usage, and contextual upsell.
    """
    sub = await get_active_subscription(current_user.id, db)
    usage = await get_monthly_usage(current_user.id, db)
    return compute_entitlements(current_user, sub, usage)


@router.get("/usage", response_model=UsageResponse)
async def get_usage(current_user: CurrentUser, db: DB):
    """
    Return current month usage stats for the authenticated user.
    Includes message count, tokens, cost, and credit balance.
    """
    from api.services.billing_service import PLANS_CONFIG
    usage = await get_monthly_usage(current_user.id, db)
    plan_cfg = PLANS_CONFIG.get(current_user.plan, PLANS_CONFIG["free"])
    limit = plan_cfg["limits"]["ai_messages_per_month"]
    count = usage["messages_count"]
    usage_pct = -1.0 if limit == -1 else round((count / limit) * 100, 1) if limit > 0 else 0.0
    return UsageResponse(
        month=usage["month"],
        messages_count=count,
        messages_limit=limit,
        usage_pct=usage_pct,
        tokens_total=usage["tokens_total"],
        cost_usd_total=usage["cost_usd_total"],
        credits_remaining=current_user.credits,
    )


@router.get("/upsell")
async def get_upsell(current_user: CurrentUser, db: DB):
    """
    Return a contextual upsell suggestion based on plan and current usage.
    Returns null if already on highest tier.
    """
    usage = await get_monthly_usage(current_user.id, db)
    return get_upsell_suggestion(current_user.plan, usage)


@router.post("/checkout-session", response_model=CheckoutResponse)
async def create_checkout_session(body: CheckoutRequest, current_user: CurrentUser, db: DB):
    """
    Create a Stripe Checkout session for subscription upgrade.
    Plan and price resolved server-side only — client provides slug + interval.
    """
    plan_cfg = PLANS_CONFIG.get(body.plan)
    if not plan_cfg:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan}")

    price_key = f"stripe_price_{body.interval}"
    price_id: str | None = plan_cfg.get(price_key)
    if not price_id:
        logger.error(
            f"[billing] Missing Stripe price ID for plan={body.plan} interval={body.interval}. "
            "Run stripe/setup_stripe.py and set STRIPE_PRICE_* in .env"
        )
        raise HTTPException(
            status_code=503,
            detail=f"Paiement temporairement indisponible pour le plan '{body.plan}' ({body.interval}). "
                   "Contacte le support.",
        )

    customer_id = await get_or_create_stripe_customer(current_user, db)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        client_reference_id=str(current_user.id),  # links webhook back to our user
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=settings.STRIPE_CHECKOUT_SUCCESS_URL,
        cancel_url=settings.STRIPE_CHECKOUT_CANCEL_URL,
        subscription_data={
            "metadata": {"user_id": str(current_user.id), "plan": body.plan},
        },
    )
    logger.info(f"[billing] Checkout session {session.id} created for user {current_user.id}")
    return CheckoutResponse(url=session.url)


@router.post("/module-checkout-session", response_model=CheckoutResponse)
async def create_module_checkout_session(
    body: ModuleCheckoutRequest, current_user: CurrentUser, db: DB
):
    """
    Create a Stripe Checkout session for a single module purchase.
    Module slug resolved server-side from MODULES_CONFIG only.
    """
    mod_cfg = MODULES_CONFIG.get(body.module)
    if not mod_cfg:
        raise HTTPException(status_code=400, detail=f"Unknown module: {body.module}")

    price_id: str | None = mod_cfg.get("stripe_price_id")
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Module '{body.module}' is not yet configured for individual purchase. "
                   "Use a Pro or Business plan to access all modules.",
        )

    customer_id = await get_or_create_stripe_customer(current_user, db)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        client_reference_id=str(current_user.id),
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=settings.STRIPE_CHECKOUT_SUCCESS_URL,
        cancel_url=settings.STRIPE_CHECKOUT_CANCEL_URL,
        subscription_data={
            "metadata": {
                "user_id": str(current_user.id),
                "module": body.module,
                "type": "module",
            },
        },
    )
    logger.info(
        f"[billing] Module checkout session {session.id} created "
        f"for user {current_user.id} module={body.module}"
    )
    return CheckoutResponse(url=session.url)


async def create_portal_session(current_user: CurrentUser, db: DB):
    """Open Stripe Billing Portal so user can manage/cancel their subscription."""
    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No active subscription found. Subscribe first.",
        )
    session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=settings.STRIPE_PORTAL_RETURN_URL,
    )
    return PortalResponse(url=session.url)


@router.post("/credits/purchase", response_model=CreditPurchaseResponse)
async def purchase_credits(
    body: CreditPurchaseRequest, current_user: CurrentUser, db: DB
):
    """
    Create a one-time Stripe Checkout session to purchase credit packs.
    Each pack = STRIPE_CREDIT_PACK_SIZE credits.
    """
    if not settings.STRIPE_CREDIT_PRICE_ID:
        raise HTTPException(status_code=503, detail="Credit purchases not configured.")

    customer_id = await get_or_create_stripe_customer(current_user, db)
    credits_to_add = body.quantity * settings.STRIPE_CREDIT_PACK_SIZE

    session = stripe.checkout.Session.create(
        customer=customer_id,
        client_reference_id=str(current_user.id),
        payment_method_types=["card"],
        line_items=[{"price": settings.STRIPE_CREDIT_PRICE_ID, "quantity": body.quantity}],
        mode="payment",
        success_url=settings.STRIPE_CHECKOUT_SUCCESS_URL + f"&credits={credits_to_add}",
        cancel_url=settings.STRIPE_CHECKOUT_CANCEL_URL,
        metadata={"type": "credits", "user_id": str(current_user.id), "credits": str(credits_to_add)},
    )
    return CreditPurchaseResponse(url=session.url, credits_to_add=credits_to_add)


# ─── Add-on packs ─────────────────────────────────────────────────────────────

@router.get("/addons", response_model=list[AddonPublic])
async def list_addons():
    """Return all available add-on packs (API calls, storage, credits)."""
    return [
        AddonPublic(slug=slug, **{k: v for k, v in cfg.items() if k != "stripe_price_id"})
        for slug, cfg in ADDONS_CONFIG.items()
    ]


@router.post("/addon/checkout", response_model=AddonCheckoutResponse)
async def addon_checkout(body: AddonCheckoutRequest, current_user: CurrentUser, db: DB):
    """
    Create a Stripe Checkout session for an add-on pack.
    Slug is validated server-side — client never controls price or type.
    """
    addon_cfg = ADDONS_CONFIG.get(body.addon)
    if not addon_cfg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown add-on: {body.addon!r}",
        )

    price_id = addon_cfg.get("stripe_price_id")
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Add-on '{body.addon}' not yet configured in Stripe.",
        )

    customer_id = await get_or_create_stripe_customer(current_user, db)
    grants_json = str(addon_cfg["grants"])

    session = stripe.checkout.Session.create(
        customer=customer_id,
        client_reference_id=str(current_user.id),
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        success_url=settings.STRIPE_CHECKOUT_SUCCESS_URL + f"&addon={body.addon}",
        cancel_url=settings.STRIPE_CHECKOUT_CANCEL_URL,
        metadata={
            "type": "addon",
            "addon_slug": body.addon,
            "user_id": str(current_user.id),
            "grants": grants_json,
        },
    )
    return AddonCheckoutResponse(
        url=session.url,
        addon_name=addon_cfg["name"],
        price_usd=addon_cfg["price_usd"],
    )


# ─── Stripe webhook — raw body, sig-verified, idempotent ─────────────────────

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    db: DB,
    stripe_signature: Annotated[str | None, Header(alias="stripe-signature")] = None,
):
    """
    Stripe webhook endpoint.
    CRITICAL: reads raw body BEFORE any parsing — required for sig verification.
    Idempotent: duplicate events are silently acknowledged (HTTP 200).
    """
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    payload = await request.body()  # raw bytes — must not be parsed first

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("[webhook] Invalid Stripe signature — rejecting")
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as exc:
        logger.error(f"[webhook] Malformed payload: {exc}")
        raise HTTPException(status_code=400, detail="Malformed payload")

    event_id = event["id"]
    event_type = event["type"]

    # Idempotency check — return 200 immediately for already-processed events
    if await is_event_processed(event_id, db):
        logger.info(f"[webhook] Duplicate event {event_id} — acknowledged, skipping")
        return {"received": True, "status": "duplicate"}

    logger.info(f"[webhook] Processing {event_type} id={event_id}")
    error: str | None = None

    try:
        data = event["data"]["object"]

        if event_type == "checkout.session.completed":
            await handle_checkout_completed(data, db)

        elif event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            await sync_subscription_from_stripe(data, db)

            if event_type == "customer.subscription.created":
                # Look up user email to send billing confirmation
                try:
                    from sqlalchemy import select as _select
                    from api.models.user import User as _User
                    stripe_customer_id = data.get("customer")
                    result = await db.execute(
                        _select(_User).where(_User.stripe_customer_id == stripe_customer_id)
                    )
                    user = result.scalar_one_or_none()
                    if user:
                        plan = data.get("metadata", {}).get("plan", "Pro")
                        items = data.get("items", {}).get("data", [])
                        amount = items[0]["price"]["unit_amount"] / 100 if items else 0.0
                        asyncio.create_task(
                            send_billing_confirmation(user.email, plan, amount)
                        )
                except Exception as _exc:
                    logger.warning("[webhook] Could not queue billing email: %s", _exc)

        elif event_type == "customer.subscription.deleted":
            # Subscription cancelled — sync status, user.plan → free
            await sync_subscription_from_stripe(data, db)

        elif event_type == "invoice.payment_succeeded":
            # Renewal — subscription already updated by subscription.updated event
            # Log for audit / MRR tracking
            logger.info(
                f"[webhook] Payment succeeded for customer {data.get('customer')} "
                f"amount={data.get('amount_paid')} invoice={data.get('id')}"
            )

        elif event_type == "invoice.payment_failed":
            # Payment failure — Stripe will retry; subscription status updated via
            # customer.subscription.updated (status → past_due)
            logger.warning(
                f"[webhook] Payment FAILED for customer {data.get('customer')} "
                f"attempt={data.get('attempt_count')} invoice={data.get('id')}"
            )
            try:
                from sqlalchemy import select as _select
                from api.models.user import User as _User
                from api.models.subscription import Subscription as _Sub
                from api.services.subscription_state_machine import handle_payment_failed
                stripe_customer_id = data.get("customer")
                result = await db.execute(
                    _select(_User).where(_User.stripe_customer_id == stripe_customer_id)
                )
                user = result.scalar_one_or_none()
                if user:
                    sub_result = await db.execute(
                        _select(_Sub).where(_Sub.user_id == user.id)
                        .order_by(_Sub.created_at.desc()).limit(1)
                    )
                    sub = sub_result.scalar_one_or_none()
                    await handle_payment_failed(user, sub, db)
            except Exception as _exc:
                logger.warning("[webhook] Could not handle payment-failed: %s", _exc)

        elif event_type == "customer.subscription.trial_will_end":
            logger.info(f"[webhook] Trial ending soon for customer {data.get('customer')}")
            try:
                from sqlalchemy import select as _select
                from datetime import datetime, timezone
                from api.models.user import User as _User
                from api.models.subscription import Subscription as _Sub
                from api.services.subscription_state_machine import handle_trial_will_end
                stripe_customer_id = data.get("customer")
                result = await db.execute(
                    _select(_User).where(_User.stripe_customer_id == stripe_customer_id)
                )
                user = result.scalar_one_or_none()
                if user:
                    sub_result = await db.execute(
                        _select(_Sub).where(_Sub.user_id == user.id)
                        .order_by(_Sub.created_at.desc()).limit(1)
                    )
                    sub = sub_result.scalar_one_or_none()
                    trial_end_ts = data.get("trial_end")
                    days_left = 3
                    if trial_end_ts:
                        trial_end_dt = datetime.fromtimestamp(trial_end_ts, tz=timezone.utc)
                        delta = trial_end_dt - datetime.now(timezone.utc)
                        days_left = max(1, delta.days)
                    if sub:
                        await handle_trial_will_end(user, sub, days_left, db)
            except Exception as _exc:
                logger.warning("[webhook] Could not handle trial_will_end: %s", _exc)

        else:
            logger.debug(f"[webhook] Unhandled event type: {event_type}")
            await mark_event(event_id, event_type, "ignored", None, db)
            return {"received": True, "status": "ignored"}

        await mark_event(event_id, event_type, "processed", None, db)

    except Exception as exc:
        error = str(exc)
        logger.exception(f"[webhook] Error processing {event_type} id={event_id}: {exc}")
        await mark_event(event_id, event_type, "failed", error, db)
        # Return 200 to prevent Stripe from retrying non-retriable errors.
        # For transient DB errors, let it raise (Stripe will retry).

    return {"received": True, "status": "processed", "type": event_type}
