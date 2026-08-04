"""Validated, atomic, and idempotent Stripe processing for Pro Pilot."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.pilot import PilotPayment, PilotRequest
from api.services.pilot_stripe_contract_service import (
    PILOT_AMOUNT_CENTS,
    PILOT_CHECKOUT_EVENT_TYPES,
    PILOT_CURRENCY,
    PILOT_REVERSAL_EVENT_TYPES,
    PilotStripeConfig,
    PilotStripeContractError,
    VerifiedPilotCheckout,
    is_canonical_payment_link,
    load_pilot_stripe_config,
    stripe_field,
    stripe_id,
    verify_pilot_checkout_event,
    verify_pilot_reversal_event,
)


PILOT_EVENT_TYPES = PILOT_CHECKOUT_EVENT_TYPES
OPEN_REQUEST_STATES = ("pending", "processing")


async def _match_request(
    verified: VerifiedPilotCheckout,
    db: AsyncSession,
) -> PilotRequest | None:
    """Resolve only the server-issued UUID and require the paid customer email."""
    result = await db.execute(
        select(PilotRequest)
        .where(PilotRequest.id == verified.request_id)
        .with_for_update()
    )
    request = result.scalar_one_or_none()
    if request is None:
        return None
    if request.email.strip().lower() != verified.customer_email:
        return None
    return request


async def _find_payment_collisions(
    session_id: str,
    payment_intent_id: str | None,
    db: AsyncSession,
) -> tuple[PilotPayment | None, PilotPayment | None]:
    session_result = await db.execute(
        select(PilotPayment)
        .where(PilotPayment.stripe_checkout_session_id == session_id)
        .with_for_update()
    )
    session_payment = session_result.scalar_one_or_none()

    intent_payment = None
    if payment_intent_id:
        intent_result = await db.execute(
            select(PilotPayment)
            .where(PilotPayment.stripe_payment_intent_id == payment_intent_id)
            .with_for_update()
        )
        intent_payment = intent_result.scalar_one_or_none()
    return session_payment, intent_payment


async def _find_other_request_payment(
    request_id: uuid.UUID,
    session_id: str,
    db: AsyncSession,
) -> PilotPayment | None:
    result = await db.execute(
        select(PilotPayment)
        .where(
            PilotPayment.pilot_request_id == request_id,
            PilotPayment.stripe_checkout_session_id != session_id,
        )
        .with_for_update()
        .limit(1)
    )
    return result.scalar_one_or_none()


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


def _target_checkout_status(
    event_type: str,
    verified: VerifiedPilotCheckout,
) -> str:
    if event_type == "checkout.session.async_payment_failed":
        return "failed"
    if verified.paid:
        return "paid"
    return "processing"


def _transition_is_safe(current: str, target: str) -> bool:
    if current == target:
        return True
    if current == "processing" and target in {"paid", "failed"}:
        return True
    return False


async def process_pilot_checkout_event(
    event_id: str,
    event_type: str,
    session: dict[str, Any],
    db: AsyncSession,
) -> str:
    """Verify the provider contract and persist one atomic Pilot fulfillment."""
    if event_type not in PILOT_CHECKOUT_EVENT_TYPES:
        return "ignored"
    config = load_pilot_stripe_config()
    if not is_canonical_payment_link(stripe_field(session, "payment_link"), config):
        return "ignored"

    verified = await verify_pilot_checkout_event(event_id, event_type, session)
    request = await _match_request(verified, db)
    if request is None:
        raise PilotStripeContractError(
            "Pilot Checkout does not match exactly one server-side request"
        )

    provider_session = verified.session
    session_id = stripe_id(provider_session)
    if session_id is None:
        raise PilotStripeContractError("Pilot Checkout Session id is missing")
    payment_intent_id = verified.payment_intent_id
    session_payment, intent_payment = await _find_payment_collisions(
        session_id,
        payment_intent_id,
        db,
    )
    if (
        session_payment is not None
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

    other_request_payment = await _find_other_request_payment(
        request.id,
        session_id,
        db,
    )
    if other_request_payment is not None:
        return await _mark_collision_manual_review(
            session_payment,
            other_request_payment,
            request,
            db,
        )

    target_status = _target_checkout_status(event_type, verified)
    if session_payment is not None:
        if session_payment.status == "paid" and target_status in {
            "paid",
            "processing",
        }:
            return "duplicate"
        if not _transition_is_safe(session_payment.status, target_status):
            return await _mark_collision_manual_review(
                session_payment,
                intent_payment,
                request,
                db,
            )
    elif request.status not in OPEN_REQUEST_STATES:
        request.status = "manual_review"
        await db.flush()
        return "manual_review"

    payment_status = str(stripe_field(provider_session, "payment_status") or "")
    payment = session_payment
    is_new = payment is None
    if is_new:
        payment = PilotPayment(
            pilot_request_id=request.id,
            stripe_checkout_session_id=session_id,
            stripe_payment_intent_id=payment_intent_id,
            stripe_event_id=event_id,
            stripe_payment_link_id=config.payment_link_id,
            stripe_price_id=config.price_id,
            customer_email=verified.customer_email,
            currency=PILOT_CURRENCY,
            amount_subtotal=PILOT_AMOUNT_CENTS,
            payment_status=payment_status,
            status=target_status,
            livemode=config.livemode,
        )
    assert payment is not None

    for _ in range(2):
        savepoint = await db.begin_nested()
        try:
            if is_new:
                db.add(payment)
            else:
                payment.stripe_event_id = event_id
                payment.stripe_payment_intent_id = payment_intent_id
                payment.payment_status = payment_status
                payment.amount_subtotal = PILOT_AMOUNT_CENTS
                payment.status = target_status
                payment.customer_email = verified.customer_email
            request.status = target_status
            await db.flush()
            await savepoint.commit()
            return target_status
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
            or session_payment.stripe_payment_intent_id
            not in (None, payment_intent_id)
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


def _reversal_payment_intent_id(event_type: str, value: Any) -> str | None:
    if event_type == "payment_intent.canceled":
        return stripe_id(value)
    return stripe_id(stripe_field(value, "payment_intent"))


def _validate_stored_payment_contract(
    payment: PilotPayment,
    config: PilotStripeConfig,
) -> None:
    if (
        payment.stripe_payment_link_id != config.payment_link_id
        or payment.stripe_price_id != config.price_id
        or payment.currency.lower() != PILOT_CURRENCY
        or payment.amount_subtotal != PILOT_AMOUNT_CENTS
        or payment.livemode != config.livemode
    ):
        raise PilotStripeContractError("Stored Pilot payment contract mismatch")


def _reversal_target_status(event_type: str, value: Any) -> tuple[str, str]:
    if event_type in {"charge.refunded", "refund.created", "refund.updated"}:
        if event_type == "charge.refunded":
            amount = stripe_field(value, "amount_refunded")
            refund_status = "succeeded"
        else:
            amount = stripe_field(value, "amount")
            refund_status = str(stripe_field(value, "status") or "")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise PilotStripeContractError("Pilot refund amount is invalid")
        if not 0 < amount <= PILOT_AMOUNT_CENTS:
            raise PilotStripeContractError("Pilot refund amount is outside the contract")
        if refund_status not in {"pending", "requires_action", "succeeded"}:
            raise PilotStripeContractError("Pilot refund status is invalid")
        if amount == PILOT_AMOUNT_CENTS and refund_status == "succeeded":
            return "failed", "refunded"
        return "manual_review", "partially_refunded"

    if event_type == "charge.dispute.created":
        return "manual_review", "disputed"
    if event_type == "charge.dispute.closed":
        dispute_status = str(stripe_field(value, "status") or "")
        if dispute_status == "lost":
            return "failed", "dispute_lost"
        return "manual_review", "dispute_closed"
    if event_type == "payment_intent.canceled":
        return "failed", "canceled"
    raise PilotStripeContractError("Unsupported Pilot reversal event")


async def process_pilot_reversal_event(
    event_id: str,
    event_type: str,
    signed_object: dict[str, Any],
    db: AsyncSession,
) -> str:
    """Downgrade an existing Pilot payment; never reactivate automatically."""
    if event_type not in PILOT_REVERSAL_EVENT_TYPES:
        return "ignored"
    signed_intent_id = _reversal_payment_intent_id(event_type, signed_object)
    if not signed_intent_id:
        return "ignored"
    result = await db.execute(
        select(PilotPayment)
        .where(PilotPayment.stripe_payment_intent_id == signed_intent_id)
        .with_for_update()
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        return "ignored"

    provider_object, config = await verify_pilot_reversal_event(
        event_id,
        event_type,
        signed_object,
    )
    provider_intent_id = _reversal_payment_intent_id(event_type, provider_object)
    if provider_intent_id != signed_intent_id:
        raise PilotStripeContractError("Pilot reversal PaymentIntent mismatch")
    if bool(stripe_field(provider_object, "livemode")) != config.livemode:
        raise PilotStripeContractError("Pilot reversal livemode mismatch")
    currency = stripe_field(provider_object, "currency")
    if currency is not None and str(currency).lower() != PILOT_CURRENCY:
        raise PilotStripeContractError("Pilot reversal currency mismatch")
    _validate_stored_payment_contract(payment, config)

    request = None
    if payment.pilot_request_id is not None:
        request_result = await db.execute(
            select(PilotRequest)
            .where(PilotRequest.id == payment.pilot_request_id)
            .with_for_update()
        )
        request = request_result.scalar_one_or_none()
    target_status, payment_status = _reversal_target_status(
        event_type,
        provider_object,
    )
    payment.stripe_event_id = event_id
    payment.status = target_status
    payment.payment_status = payment_status
    if request is not None:
        request.status = target_status
    await db.flush()
    return target_status
