"""
backend/api/routers/billing.py
Stripe billing — checkout, webhook, portal
SECURITY: webhook signature verified on every call
"""
from __future__ import annotations

import logging
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from backend.api.config import settings
from backend.api.deps import get_current_user, get_db
from backend.api.models import User

logger = logging.getLogger(__name__)
router = APIRouter()

stripe.api_key = settings.STRIPE_SECRET_KEY


class CheckoutRequest(BaseModel):
    plan: str  # "pro" | "business"


PLAN_PRICE_MAP = {
    "pro": settings.STRIPE_PRICE_PRO_MONTHLY_ID,
    "business": settings.STRIPE_PRICE_BUSINESS_MONTHLY_ID,
}


@router.post("/checkout-session")
async def create_checkout_session(
    body: CheckoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    price_id = PLAN_PRICE_MAP.get(body.plan)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan}")

    session = stripe.checkout.Session.create(
        customer_email=current_user.email,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=settings.STRIPE_CHECKOUT_SUCCESS_URL,
        cancel_url=settings.STRIPE_CHECKOUT_CANCEL_URL,
        metadata={"user_id": str(current_user.id), "tenant_id": str(current_user.tenant_id)},
        idempotency_key=f"checkout-{current_user.id}-{body.plan}",
    )
    return {"url": session.url}


@router.post("/portal")
async def customer_portal(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer linked")
    session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=settings.STRIPE_PORTAL_RETURN_URL,
    )
    return {"url": session.url}


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="stripe-signature")] = None,
):
    """
    CRITICAL: Must verify Stripe signature.
    Never process webhook events without this check.
    """
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Webhook parse error: {e}")
        raise HTTPException(status_code=400, detail="Webhook error")

    event_type = event["type"]
    logger.info(f"[webhook] received event_type={event_type} id={event['id']}")

    # Dispatch handlers
    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "invoice.payment_failed": _handle_payment_failed,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            await handler(event["data"]["object"])
        except Exception as e:
            logger.error(f"[webhook] handler error event={event_type} err={e}")
            # Return 200 anyway — Stripe will retry if we return 5xx
            # Log for manual investigation

    return {"received": True}


async def _handle_checkout_completed(session: dict) -> None:
    user_id = session.get("metadata", {}).get("user_id")
    tenant_id = session.get("metadata", {}).get("tenant_id")
    stripe_customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    logger.info(f"[checkout_completed] user={user_id} sub={subscription_id}")
    # TODO: db.update subscription status, send confirmation email


async def _handle_subscription_updated(subscription: dict) -> None:
    sub_id = subscription.get("id")
    status = subscription.get("status")
    logger.info(f"[sub_updated] id={sub_id} status={status}")
    # TODO: db.update subscription status


async def _handle_subscription_deleted(subscription: dict) -> None:
    sub_id = subscription.get("id")
    logger.info(f"[sub_deleted] id={sub_id}")
    # TODO: db.mark subscription cancelled, revoke module access


async def _handle_payment_failed(invoice: dict) -> None:
    customer_id = invoice.get("customer")
    amount = invoice.get("amount_due", 0)
    logger.warning(f"[payment_failed] customer={customer_id} amount={amount/100}$")
    # TODO: send dunning email, flag account
