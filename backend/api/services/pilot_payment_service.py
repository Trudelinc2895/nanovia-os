"""Validated and idempotent Stripe processing for Nanovia Pro Pilot."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import stripe
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models.pilot import PilotPayment, PilotRequest


PILOT_EVENT_TYPES = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
}
OPEN_REQUEST_STATES = ("pending", "processing")


def _stripe_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        candidate = value.get("id")
        return str(candidate) if candidate else None
    candidate = getattr(value, "id", None)
    return str(candidate) if candidate else None


def _normalized_email(session: dict[str, Any]) -> str | None:
    details = session.get("customer_details") or {}
    email = details.get("email") or session.get("customer_email")
    return str(email).strip().lower() if email else None


async def retrieve_pilot_line_items(session_id: str) -> Any:
    """Retrieve Checkout line items; tests replace this boundary with local data."""
    return await asyncio.to_thread(
        stripe.checkout.Session.list_line_items,
        session_id,
        limit=100,
        expand=["data.price"],
    )


def _line_item_data(response: Any) -> list[Any]:
    if isinstance(response, dict):
        return list(response.get("data") or [])
    return list(getattr(response, "data", []) or [])


async def _match_request(
    session: dict[str, Any], customer_email: str | None, db: AsyncSession
) -> tuple[PilotRequest | None, bool]:
    reference = session.get("client_reference_id")
    if reference:
        try:
            request_uuid = uuid.UUID(str(reference))
        except (TypeError, ValueError):
            request_uuid = None
        if request_uuid is not None:
            result = await db.execute(
                select(PilotRequest).where(
                    PilotRequest.id == request_uuid,
                    PilotRequest.status.in_(OPEN_REQUEST_STATES),
                )
            )
            request = result.scalar_one_or_none()
            if request is not None:
                if customer_email and request.email.lower() != customer_email:
                    return None, True
                return request, False

    if not customer_email:
        return None, False

    result = await db.execute(
        select(PilotRequest).where(
            func.lower(PilotRequest.email) == customer_email,
            PilotRequest.status.in_(OPEN_REQUEST_STATES),
        )
    )
    matches = list(result.scalars().all())
    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1


async def _find_payment_collisions(
    session_id: str,
    payment_intent_id: str | None,
    db: AsyncSession,
) -> tuple[PilotPayment | None, PilotPayment | None]:
    session_result = await db.execute(
        select(PilotPayment).where(
            PilotPayment.stripe_checkout_session_id == session_id
        )
    )
    session_payment = session_result.scalar_one_or_none()

    intent_payment = None
    if payment_intent_id:
        intent_result = await db.execute(
            select(PilotPayment).where(
                PilotPayment.stripe_payment_intent_id == payment_intent_id
            )
        )
        intent_payment = intent_result.scalar_one_or_none()
    return session_payment, intent_payment


def _same_payment(
    left: PilotPayment | None,
    right: PilotPayment | None,
) -> bool:
    if left is None or right is None:
        return False
    if left is right:
        return True
    return left.id is not None and left.id == right.id


async def _mark_collision_manual_review(
    session_payment: PilotPayment | None,
    intent_payment: PilotPayment | None,
    matched_request: PilotRequest | None,
    db: AsyncSession,
) -> str:
    payments = [
        payment
        for index, payment in enumerate((session_payment, intent_payment))
        if payment is not None
        and not any(
            _same_payment(payment, previous)
            for previous in (session_payment, intent_payment)[:index]
        )
    ]
    request_ids = {
        payment.pilot_request_id
        for payment in payments
        if payment.pilot_request_id is not None
    }
    for payment in payments:
        payment.status = "manual_review"
    if matched_request is not None:
        matched_request.status = "manual_review"
        request_ids.discard(matched_request.id)
    if request_ids:
        requests_result = await db.execute(
            select(PilotRequest).where(PilotRequest.id.in_(request_ids))
        )
        for request in requests_result.scalars().all():
            request.status = "manual_review"
    await db.flush()
    return "manual_review"


async def process_pilot_checkout_event(
    event_id: str,
    event_type: str,
    session: dict[str, Any],
    db: AsyncSession,
) -> str:
    """Validate a Pilot Checkout event and persist one payment per Session."""
    if event_type not in PILOT_EVENT_TYPES:
        return "ignored"
    if (
        not settings.STRIPE_PILOT_PAYMENT_LINK_ID
        or not settings.STRIPE_PILOT_PRICE_ID
        or not settings.STRIPE_PILOT_PRODUCT_ID
    ):
        raise RuntimeError("Pilot Stripe identifiers are not configured")
    if _stripe_id(session.get("payment_link")) != settings.STRIPE_PILOT_PAYMENT_LINK_ID:
        return "ignored"

    # The webhook signing secret authenticates the owning standard Stripe
    # account. STRIPE_ACCOUNT_ID remains an inventory/configuration guard; an
    # event.account check only applies to Connect events where that field exists.
    session_id = _stripe_id(session.get("id"))
    if not session_id or session.get("mode") != "payment":
        return "ignored"
    if bool(session.get("livemode")) != (settings.APP_ENV == "production"):
        return "ignored"
    if str(session.get("currency") or "").lower() != "cad":
        return "ignored"

    line_items = _line_item_data(await retrieve_pilot_line_items(session_id))
    if len(line_items) != 1:
        return "ignored"
    line_item = line_items[0]
    price = line_item.get("price") if isinstance(line_item, dict) else getattr(line_item, "price", None)
    price_id = _stripe_id(price)
    if price_id != settings.STRIPE_PILOT_PRICE_ID:
        return "ignored"
    price_currency = price.get("currency") if isinstance(price, dict) else getattr(price, "currency", None)
    price_recurring = price.get("recurring") if isinstance(price, dict) else getattr(price, "recurring", None)
    price_type = price.get("type") if isinstance(price, dict) else getattr(price, "type", None)
    price_product = price.get("product") if isinstance(price, dict) else getattr(price, "product", None)
    product_id = _stripe_id(price_product)
    quantity = line_item.get("quantity") if isinstance(line_item, dict) else getattr(line_item, "quantity", None)
    if (
        str(price_currency or "").lower() != "cad"
        or price_recurring
        or (price_type is not None and price_type != "one_time")
        or quantity != 1
    ):
        return "ignored"
    if product_id is not None and product_id != settings.STRIPE_PILOT_PRODUCT_ID:
        return "ignored"

    payment_status = str(session.get("payment_status") or "unknown")
    if event_type == "checkout.session.async_payment_failed":
        target_status = "failed"
    elif payment_status == "paid":
        target_status = "paid"
    else:
        target_status = "processing"

    customer_email = _normalized_email(session)
    request, ambiguous = await _match_request(session, customer_email, db)
    if request is None:
        target_status = "manual_review"

    payment_intent_id = _stripe_id(session.get("payment_intent"))
    session_payment, intent_payment = await _find_payment_collisions(
        session_id,
        payment_intent_id,
        db,
    )
    if (
        session_payment is not None
        and payment_intent_id is not None
        and session_payment.stripe_payment_intent_id not in (None, payment_intent_id)
    ):
        return await _mark_collision_manual_review(
            session_payment,
            intent_payment,
            request,
            db,
        )
    if intent_payment is not None and not _same_payment(
        session_payment,
        intent_payment,
    ):
        return await _mark_collision_manual_review(
            session_payment,
            intent_payment,
            request,
            db,
        )
    if session_payment is not None and session_payment.status == "paid":
        return "duplicate"

    amount_subtotal = (
        line_item.get("amount_subtotal")
        if isinstance(line_item, dict)
        else getattr(line_item, "amount_subtotal", None)
    )
    payment = session_payment
    is_new = payment is None
    if is_new:
        payment = PilotPayment(
            pilot_request_id=request.id if request else None,
            stripe_checkout_session_id=session_id,
            stripe_payment_intent_id=payment_intent_id,
            stripe_event_id=event_id,
            stripe_payment_link_id=settings.STRIPE_PILOT_PAYMENT_LINK_ID,
            stripe_price_id=settings.STRIPE_PILOT_PRICE_ID,
            customer_email=customer_email,
            currency="cad",
            amount_subtotal=amount_subtotal,
            payment_status=payment_status,
            status=target_status,
            livemode=bool(session.get("livemode")),
        )
    assert payment is not None

    for attempt in range(2):
        savepoint = await db.begin_nested()
        try:
            if is_new:
                db.add(payment)
            else:
                payment.stripe_event_id = event_id
                payment.stripe_payment_intent_id = (
                    payment.stripe_payment_intent_id or payment_intent_id
                )
                payment.payment_status = payment_status
                payment.amount_subtotal = amount_subtotal
                payment.status = target_status
                if payment.pilot_request_id is None and request is not None:
                    payment.pilot_request_id = request.id
            if request is not None:
                request.status = target_status
            await db.flush()
            await savepoint.commit()
            return "manual_review" if ambiguous else target_status
        except IntegrityError:
            await savepoint.rollback()

        session_payment, intent_payment = await _find_payment_collisions(
            session_id,
            payment_intent_id,
            db,
        )
        if (
            session_payment is None
            or (
                intent_payment is not None
                and not _same_payment(session_payment, intent_payment)
            )
            or (
                payment_intent_id is not None
                and session_payment.stripe_payment_intent_id
                not in (None, payment_intent_id)
            )
        ):
            return await _mark_collision_manual_review(
                session_payment,
                intent_payment,
                request,
                db,
            )
        if session_payment.status == "paid":
            return "duplicate"
        payment = session_payment
        is_new = False

    raise RuntimeError("Pilot payment collision could not be resolved safely")
