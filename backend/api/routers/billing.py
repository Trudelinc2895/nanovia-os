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

import logging
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.core.deps import CurrentUser, DB
from api.core.monetization import (
    getEntitlements as monetization_get_entitlements,
    getUsageSnapshot as monetization_get_usage_snapshot,
)
from api.core.monetization.webhook_handler_service import handle_stripe_webhook
from api.core.monetization.pricing_config_service import get_pricing_catalog
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
    PortalSessionRequest,
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
    has_feature,
)
from api.services.entitlements_service import get_effective_plan
from api.services.module_registry import canonicalize_module_slug
from api.services.turnstile_service import enforce_turnstile
from api.services.usage_service import get_monthly_usage

logger = logging.getLogger(__name__)
router = APIRouter()
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = "2026-04-22.dahlia"

# ── Prometheus counters (graceful fallback) ───────────────────────────────────
try:
    from prometheus_client import Counter
    _payment_errors = Counter(
        "kt_payment_errors_total", "Stripe payment / checkout errors", ["reason"]
    )
    _module_purchases = Counter(
        "kt_module_purchases_total", "Module subscription purchases completed", ["module"]
    )
    _plan_purchases = Counter(
        "kt_plan_purchases_total", "Plan subscription purchases completed", ["plan", "interval"]
    )
    _webhook_errors = Counter(
        "kt_webhook_errors_total", "Stripe webhook processing errors", ["event_type"]
    )
    _quota_exceeded = Counter(
        "kt_quota_exceeded_total", "Requests blocked by quota limit", ["plan"]
    )
    _HAS_PROM = True
except Exception:
    _HAS_PROM = False


# ─── Public ───────────────────────────────────────────────────────────────────

@router.get("/plans", response_model=list[PlanPublic])
async def list_plans() -> list[PlanPublic]:
    """Return all available plans with pricing, limits, and feature gates."""
    catalog = get_pricing_catalog()
    return [
        PlanPublic(
            slug=slug,
            name=cfg["name"],
            marketing_description=cfg["marketing_description"],
            highlight=cfg["highlight"],
            price_monthly_usd=cfg["price_monthly_usd"],
            price_yearly_usd=cfg["price_yearly_usd"],
            yearly_discount_pct=cfg["yearly_discount_pct"],
            trial_days=cfg["trial_days"],
            support_level=cfg["support_level"],
            limits=cfg["limits"],
            features=cfg["features"],
            features_enabled=cfg["features_enabled"],
            included_modules=cfg["included_modules"],
        )
        for slug, cfg in catalog["plans"].items()
    ]


@router.get("/modules", response_model=list[ModulePublic])
async def list_modules() -> list[ModulePublic]:
    """Return all available à-la-carte modules with pricing."""
    catalog = get_pricing_catalog()
    return [
        ModulePublic(
            slug=cfg["slug"],
            name=cfg["name"],
            price_usd=cfg["price_usd"],
            description=cfg["description"],
            available=bool(cfg.get("stripe_price_id")),
            included_in_plans=cfg["included_in_plans"],
        )
        for cfg in catalog["modules"].values()
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

    effective_plan = await get_effective_plan(current_user, db)
    plan_modules = {
        slug for slug, cfg in MODULES_CONFIG.items()
        if effective_plan in cfg.get("included_in_plans", [])
    }

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
        "plan": effective_plan,
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
    return await monetization_get_entitlements(str(current_user.id), db)


@router.get("/usage", response_model=UsageResponse)
async def get_usage(current_user: CurrentUser, db: DB):
    """
    Return current month usage stats for the authenticated user.
    Includes message count, tokens, cost, and credit balance.
    """
    snapshot = await monetization_get_usage_snapshot(str(current_user.id), db)
    usage = snapshot["usage_this_month"]
    quota = snapshot["quota"]["ai_messages"]
    return UsageResponse(
        month=usage["month"],
        messages_count=usage["messages_count"],
        messages_limit=quota["limit"],
        usage_pct=quota["pct_used"],
        tokens_total=usage["tokens_total"],
        cost_usd_total=usage["cost_usd_total"],
        credits_remaining=snapshot["credits"],
    )


@router.get("/upsell")
async def get_upsell(current_user: CurrentUser, db: DB):
    """
    Return a contextual upsell suggestion based on plan and current usage.
    Returns null if already on highest tier.
    """
    usage = await get_monthly_usage(current_user.id, db)
    effective_plan = await get_effective_plan(current_user, db)
    return get_upsell_suggestion(effective_plan, usage)


@router.post("/checkout-session", response_model=CheckoutResponse)
async def create_checkout_session(body: CheckoutRequest, request: Request, current_user: CurrentUser, db: DB):
    """
    Create a Stripe Checkout session for subscription upgrade.
    Plan and price resolved server-side only — client provides slug + interval.
    """
    await enforce_turnstile(request, body.turnstile_token, surface="billing")
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
        if _HAS_PROM:
            _payment_errors.labels(reason="missing_price_id").inc()
        raise HTTPException(
            status_code=503,
            detail=f"Paiement temporairement indisponible pour le plan '{body.plan}' ({body.interval}). "
                   "Contacte le support.",
        )

    try:
        customer_id = await get_or_create_stripe_customer(current_user, db)
        session = stripe.checkout.Session.create(
            customer=customer_id,
            client_reference_id=str(current_user.id),
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=settings.STRIPE_CHECKOUT_SUCCESS_URL,
            cancel_url=settings.STRIPE_CHECKOUT_CANCEL_URL,
            subscription_data={
                "metadata": {"user_id": str(current_user.id), "plan": body.plan},
            },
        )
    except stripe.StripeError as exc:
        logger.error("[billing] Stripe error creating checkout for plan=%s: %s", body.plan, exc)
        if _HAS_PROM:
            _payment_errors.labels(reason="stripe_api_error").inc()
        raise HTTPException(status_code=503, detail="Erreur Stripe — réessaie dans quelques instants.")
    logger.info(
        "[billing] Plan checkout session %s created user=%s plan=%s interval=%s",
        session.id, current_user.id, body.plan, body.interval,
    )
    return CheckoutResponse(url=session.url)


@router.post("/module-checkout-session", response_model=CheckoutResponse)
async def create_module_checkout_session(
    body: ModuleCheckoutRequest, request: Request, current_user: CurrentUser, db: DB
):
    """
    Create a Stripe Checkout session for a single module purchase.
    Module slug resolved server-side from MODULES_CONFIG only.
    """
    await enforce_turnstile(request, body.turnstile_token, surface="billing")
    module_slug = canonicalize_module_slug(body.module)
    mod_cfg = MODULES_CONFIG.get(module_slug) if module_slug else None
    if not mod_cfg:
        raise HTTPException(status_code=400, detail=f"Unknown module: {body.module}")

    price_id: str | None = mod_cfg.get("stripe_price_id")
    if not price_id:
        if _HAS_PROM:
            _payment_errors.labels(reason="module_price_not_configured").inc()
        raise HTTPException(
            status_code=503,
            detail=f"Module '{body.module}' is not yet configured for individual purchase. "
                   "Use a Pro or Business plan to access all modules.",
        )

    try:
        customer_id = await get_or_create_stripe_customer(current_user, db)
        session = stripe.checkout.Session.create(
            customer=customer_id,
            client_reference_id=str(current_user.id),
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=settings.STRIPE_CHECKOUT_SUCCESS_URL,
            cancel_url=settings.STRIPE_CHECKOUT_CANCEL_URL,
            subscription_data={
                "metadata": {
                    "user_id": str(current_user.id),
                    "module": module_slug,
                    "type": "module",
                },
            },
        )
    except stripe.StripeError as exc:
        logger.error("[billing] Stripe error creating module checkout module=%s: %s", module_slug, exc)
        if _HAS_PROM:
            _payment_errors.labels(reason="stripe_api_error").inc()
        raise HTTPException(status_code=503, detail="Erreur Stripe — réessaie dans quelques instants.")
    logger.info(
        "[billing] Module checkout session %s created user=%s module=%s",
        session.id, current_user.id, module_slug,
    )
    return CheckoutResponse(url=session.url)


@router.post("/portal-session", response_model=PortalResponse)
async def create_portal_session(
    request: Request,
    current_user: CurrentUser,
    db: DB,
    body: PortalSessionRequest | None = None,
):
    """Open Stripe Billing Portal so user can manage/cancel their subscription."""
    await enforce_turnstile(request, body.turnstile_token if body else None, surface="billing")
    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No active subscription found. Subscribe first.",
        )
    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=settings.STRIPE_PORTAL_RETURN_URL,
        )
    except stripe.StripeError as exc:
        logger.error("[billing] Stripe error creating portal session for user=%s: %s", current_user.id, exc)
        if _HAS_PROM:
            _payment_errors.labels(reason="stripe_api_error").inc()
        raise HTTPException(status_code=503, detail="Erreur Stripe — réessaie dans quelques instants.")
    return PortalResponse(url=session.url)


@router.post("/credits/purchase", response_model=CreditPurchaseResponse)
async def purchase_credits(
    body: CreditPurchaseRequest, request: Request, current_user: CurrentUser, db: DB
):
    """
    Create a one-time Stripe Checkout session to purchase credit packs.
    Each pack = STRIPE_CREDIT_PACK_SIZE credits.
    """
    await enforce_turnstile(request, body.turnstile_token, surface="billing")
    if not settings.STRIPE_CREDIT_PRICE_ID:
        raise HTTPException(status_code=503, detail="Credit purchases not configured.")

    credits_to_add = body.quantity * settings.STRIPE_CREDIT_PACK_SIZE

    try:
        customer_id = await get_or_create_stripe_customer(current_user, db)
        session = stripe.checkout.Session.create(
            customer=customer_id,
            client_reference_id=str(current_user.id),
            line_items=[{"price": settings.STRIPE_CREDIT_PRICE_ID, "quantity": body.quantity}],
            mode="payment",
            success_url=settings.STRIPE_CHECKOUT_SUCCESS_URL + f"&credits={credits_to_add}",
            cancel_url=settings.STRIPE_CHECKOUT_CANCEL_URL,
            metadata={"type": "credits", "user_id": str(current_user.id), "credits": str(credits_to_add)},
        )
    except stripe.StripeError as exc:
        logger.error("[billing] Stripe error creating credits checkout user=%s: %s", current_user.id, exc)
        if _HAS_PROM:
            _payment_errors.labels(reason="stripe_api_error").inc()
        raise HTTPException(status_code=503, detail="Erreur Stripe — réessaie dans quelques instants.")
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
async def addon_checkout(body: AddonCheckoutRequest, request: Request, current_user: CurrentUser, db: DB):
    """
    Create a Stripe Checkout session for an add-on pack.
    Slug is validated server-side — client never controls price or type.
    """
    await enforce_turnstile(request, body.turnstile_token, surface="billing")
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

    grants_json = str(addon_cfg["grants"])

    try:
        customer_id = await get_or_create_stripe_customer(current_user, db)
        session = stripe.checkout.Session.create(
            customer=customer_id,
            client_reference_id=str(current_user.id),
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
    except stripe.StripeError as exc:
        logger.error("[billing] Stripe error creating addon checkout addon=%s user=%s: %s", body.addon, current_user.id, exc)
        if _HAS_PROM:
            _payment_errors.labels(reason="stripe_api_error").inc()
        raise HTTPException(status_code=503, detail="Erreur Stripe — réessaie dans quelques instants.")
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

    logger.info(f"[webhook] Processing {event_type} id={event_id}")

    try:
        result = await handle_stripe_webhook(event_id, event_type, event["data"]["object"], db)
    except Exception as exc:
        logger.exception("[webhook] Error processing %s id=%s: %s", event_type, event_id, exc)
        if _HAS_PROM:
            _webhook_errors.labels(event_type=event_type).inc()
        # Return 200 to prevent Stripe from retrying non-retriable errors.
        # For transient DB errors, let it raise (Stripe will retry).
        return {"received": True, "status": "failed", "type": event_type}

    return {"received": True, "status": result["status"], "type": event_type}
