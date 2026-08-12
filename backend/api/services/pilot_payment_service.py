"""Validated, atomic, and idempotent Stripe processing for Pro Pilot."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.pilot import PilotPayment, PilotRequest
from api.services.pilot_stripe_contract_service import (
    PILOT_AMOUNT_CENTS,
    PILOT_CHECKOUT_EVENT_TYPES,
    PILOT_CONTRACT_MARKER,
    PILOT_CURRENCY,
    PILOT_PROVIDER_MAX_ATTEMPTS,
    PILOT_PROVIDER_TIMEOUT_SECONDS,
    PILOT_REVERSAL_EVENT_TYPES,
    PILOT_STRIPE_API_VERSION,
    PilotStripeConfig,
    PilotStripeContractError,
    PilotStripeProviderUnavailable,
    VerifiedPilotCheckout,
    find_authorized_pilot_stripe_config,
    stripe_field,
    stripe_id,
    stripe_list_data,
    verify_pilot_checkout_event,
    verify_pilot_reversal_event,
)


PILOT_EVENT_TYPES = PILOT_CHECKOUT_EVENT_TYPES
OPEN_REQUEST_STATES = ("pending", "processing")
ADVERSE_STATE_PRIORITY = {
    "pending": 0,
    "processing": 0,
    "paid": 0,
    "manual_review": 1,
    "failed": 2,
}


class PilotAdverseEventPendingCommit(RuntimeError):
    """A canonical adverse event arrived before its local PilotPayment commit."""


@dataclass(frozen=True)
class PreparedPilotReversal:
    """Provider-verified reversal identity prepared before database locking."""

    signed_intent_id: str | None
    provider_object: Any | None
    config: PilotStripeConfig | None
    classification: str
    provider_sessions: tuple[Any, ...] = ()


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


async def _find_other_request_payments(
    request_id: uuid.UUID,
    session_id: str,
    db: AsyncSession,
) -> list[PilotPayment]:
    result = await db.execute(
        select(PilotPayment)
        .where(
            PilotPayment.pilot_request_id == request_id,
            PilotPayment.stripe_checkout_session_id != session_id,
        )
        .with_for_update()
    )
    return list(result.scalars().all())


def _is_retryable_failed_checkout(payment: PilotPayment) -> bool:
    """Allow only a new Session after a terminal, unpaid checkout failure."""
    return payment.status == "failed" and payment.payment_status == "unpaid"


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
        payment.status = _monotone_pilot_status(payment.status, "manual_review")
    if matched_request is not None:
        matched_request.status = _monotone_pilot_status(
            matched_request.status,
            "manual_review",
        )
        request_ids.discard(matched_request.id)
    if request_ids:
        requests_result = await db.execute(
            select(PilotRequest).where(PilotRequest.id.in_(request_ids))
        )
        for request in requests_result.scalars().all():
            request.status = _monotone_pilot_status(request.status, "manual_review")
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


def _monotone_pilot_status(*statuses: str) -> str:
    return max(statuses, key=lambda value: ADVERSE_STATE_PRIORITY.get(value, 1))


async def _apply_reversal_request_status(
    db: AsyncSession,
    *,
    payment: PilotPayment,
    request: PilotRequest,
    effective_status: str,
) -> None:
    if request.status == "paid" and effective_status in {"manual_review", "failed"}:
        other_paid_payment = await db.scalar(
            select(PilotPayment.id)
            .where(
                PilotPayment.pilot_request_id == request.id,
                PilotPayment.id != payment.id,
                PilotPayment.status == "paid",
            )
            .limit(1)
        )
        if other_paid_payment is not None:
            return
    request.status = effective_status


async def process_pilot_checkout_event(
    event_id: str,
    event_type: str,
    session: dict[str, Any],
    db: AsyncSession,
) -> str:
    """Verify the provider contract and persist one atomic Pilot fulfillment."""
    if event_type not in PILOT_CHECKOUT_EVENT_TYPES:
        return "ignored"
    config = find_authorized_pilot_stripe_config(stripe_field(session, "payment_link"))
    if config is None:
        return "ignored"

    verified = await verify_pilot_checkout_event(event_id, event_type, session)
    config = verified.config
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

    target_status = _target_checkout_status(event_type, verified)
    if session_payment is not None:
        if session_payment.status in {"manual_review", "failed"} and target_status in {
            "processing",
            "paid",
        }:
            return session_payment.status
        if session_payment.status == "paid" and target_status in {
            "paid",
            "processing",
        }:
            return "duplicate"
        if session_payment.status == "failed" and target_status == "failed":
            return "duplicate"
        if not _transition_is_safe(session_payment.status, target_status):
            return await _mark_collision_manual_review(
                session_payment,
                intent_payment,
                request,
                db,
            )

    other_request_payments = await _find_other_request_payments(
        request.id,
        session_id,
        db,
    )
    blocking_payment = next(
        (
            payment
            for payment in other_request_payments
            if not _is_retryable_failed_checkout(payment)
        ),
        None,
    )
    if blocking_payment is not None:
        return await _mark_collision_manual_review(
            session_payment,
            blocking_payment,
            request,
            db,
        )

    is_retry_after_failed_checkout = bool(other_request_payments) and all(
        _is_retryable_failed_checkout(payment)
        for payment in other_request_payments
    )
    if session_payment is None and request.status not in OPEN_REQUEST_STATES and not (
        request.status == "failed" and is_retry_after_failed_checkout
    ):
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
    if payment is None:
        raise RuntimeError("Pilot payment initialization failed")

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


async def retrieve_pilot_reversal_sessions(payment_intent_id: str) -> Any:
    """List at most two Checkout Sessions before any local row lock is acquired."""
    retryable = (stripe.error.APIConnectionError, stripe.error.RateLimitError, TimeoutError)
    for attempt in range(PILOT_PROVIDER_MAX_ATTEMPTS):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    stripe.checkout.Session.list,
                    payment_intent=payment_intent_id,
                    limit=2,
                    stripe_version=PILOT_STRIPE_API_VERSION,
                ),
                timeout=PILOT_PROVIDER_TIMEOUT_SECONDS,
            )
        except retryable as exc:
            if attempt + 1 >= PILOT_PROVIDER_MAX_ATTEMPTS:
                raise PilotStripeProviderUnavailable(
                    "Stripe reversal identity lookup was unavailable"
                ) from exc
            await asyncio.sleep(0.2 * (attempt + 1))
        except stripe.error.StripeError as exc:
            raise PilotStripeProviderUnavailable(
                "Stripe reversal identity lookup was unavailable"
            ) from exc
    raise PilotStripeProviderUnavailable("Stripe reversal identity lookup was unavailable")


def _classify_pilot_reversal_sessions(
    response: Any,
    payment_intent_id: str,
    default_config: PilotStripeConfig,
) -> tuple[str, PilotStripeConfig]:
    sessions = stripe_list_data(response)
    authorized_sessions = [
        (session, config)
        for session in sessions
        if (
            config := find_authorized_pilot_stripe_config(
                stripe_field(session, "payment_link")
            )
        )
        is not None
    ]
    if not authorized_sessions:
        return "foreign", default_config
    if len(sessions) != 1 or len(authorized_sessions) != 1:
        return "rejected", default_config
    session, config = authorized_sessions[0]
    metadata = stripe_field(session, "metadata", {}) or {}
    if (
        stripe_id(stripe_field(session, "payment_intent")) != payment_intent_id
        or stripe_field(session, "mode") != "payment"
        or bool(stripe_field(session, "livemode")) != config.livemode
        or str(stripe_field(session, "currency") or "").lower() != PILOT_CURRENCY
        or stripe_field(session, "amount_subtotal") != PILOT_AMOUNT_CENTS
        or stripe_field(session, "amount_total") != PILOT_AMOUNT_CENTS
        or stripe_field(metadata, "nanovia_contract") != PILOT_CONTRACT_MARKER
    ):
        return "rejected", config
    return "pilot", config


def _pilot_payment_for_update_statement(payment_intent_id: str):
    return (
        select(PilotPayment)
        .where(PilotPayment.stripe_payment_intent_id == payment_intent_id)
        .with_for_update()
    )


async def prepare_pilot_reversal_event(
    event_id: str,
    event_type: str,
    signed_object: Any,
) -> PreparedPilotReversal:
    """Verify and classify a reversal before starting the business transaction."""
    signed_intent_id = _reversal_payment_intent_id(event_type, signed_object)
    if not signed_intent_id:
        return PreparedPilotReversal(None, None, None, "ignored")

    provider_object, config = await verify_pilot_reversal_event(
        event_id,
        event_type,
        signed_object,
    )
    provider_intent_id = _reversal_payment_intent_id(event_type, provider_object)
    currency = stripe_field(provider_object, "currency")
    if (
        provider_intent_id != signed_intent_id
        or bool(stripe_field(provider_object, "livemode")) != config.livemode
        or (currency is not None and str(currency).lower() != PILOT_CURRENCY)
    ):
        return PreparedPilotReversal(
            signed_intent_id,
            provider_object,
            config,
            "rejected",
        )

    session_response = await retrieve_pilot_reversal_sessions(signed_intent_id)
    provider_sessions = tuple(stripe_list_data(session_response))
    classification, config = _classify_pilot_reversal_sessions(
        session_response,
        signed_intent_id,
        config,
    )
    return PreparedPilotReversal(
        signed_intent_id,
        provider_object,
        config,
        classification,
        provider_sessions,
    )


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


def _stored_session_matches_payment(payment: PilotPayment, session: Any) -> bool:
    metadata = stripe_field(session, "metadata", {}) or {}
    return (
        stripe_id(session) == payment.stripe_checkout_session_id
        and stripe_id(stripe_field(session, "payment_intent"))
        == payment.stripe_payment_intent_id
        and stripe_id(stripe_field(session, "payment_link"))
        == payment.stripe_payment_link_id
        and stripe_field(session, "mode") == "payment"
        and bool(stripe_field(session, "livemode")) == payment.livemode
        and str(stripe_field(session, "currency") or "").lower()
        == payment.currency.lower()
        and stripe_field(session, "amount_subtotal") == payment.amount_subtotal
        and stripe_field(session, "amount_total") == PILOT_AMOUNT_CENTS
        and stripe_field(metadata, "nanovia_contract") == PILOT_CONTRACT_MARKER
    )


def _reversal_target_status(
    event_type: str,
    value: Any,
) -> tuple[str | None, str]:
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
        if event_type == "refund.updated" and refund_status in {"failed", "canceled"}:
            return None, f"refund_{refund_status}"
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
    *,
    prepared_event: PreparedPilotReversal | None = None,
) -> str:
    """Downgrade an existing Pilot payment; never reactivate automatically."""
    if event_type not in PILOT_REVERSAL_EVENT_TYPES:
        return "ignored"
    prepared = prepared_event or await prepare_pilot_reversal_event(
        event_id,
        event_type,
        signed_object,
    )
    signed_intent_id = prepared.signed_intent_id
    if prepared.classification == "ignored" or not signed_intent_id:
        return "ignored"
    result = await db.execute(_pilot_payment_for_update_statement(signed_intent_id))
    payment = result.scalar_one_or_none()
    if prepared.classification == "rejected":
        return "rejected"
    if payment is None:
        if prepared.classification == "foreign":
            return "ignored"
        raise PilotAdverseEventPendingCommit(
            "Canonical Pilot payment is not committed yet"
        )
    if prepared.classification == "foreign":
        return "rejected"
    provider_object = prepared.provider_object
    config = prepared.config
    if provider_object is None or config is None:
        raise PilotStripeContractError("Prepared Pilot reversal is incomplete")
    _validate_stored_payment_contract(payment, config)
    if (
        len(prepared.provider_sessions) != 1
        or not _stored_session_matches_payment(payment, prepared.provider_sessions[0])
    ):
        return "rejected"

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
    if target_status is None:
        effective_status = _monotone_pilot_status(
            payment.status,
            request.status if request is not None else payment.status,
        )
        if effective_status in {"manual_review", "failed"}:
            payment.status = effective_status
            if request is not None:
                await _apply_reversal_request_status(
                    db,
                    payment=payment,
                    request=request,
                    effective_status=effective_status,
                )
        else:
            payment.stripe_event_id = event_id
            payment.payment_status = payment_status
        await db.flush()
        return effective_status
    effective_status = _monotone_pilot_status(
        payment.status,
        request.status if request is not None else payment.status,
        target_status,
    )
    if effective_status == target_status:
        payment.stripe_event_id = event_id
        payment.payment_status = payment_status
    payment.status = effective_status
    if request is not None:
        await _apply_reversal_request_status(
            db,
            payment=payment,
            request=request,
            effective_status=effective_status,
        )
    await db.flush()
    return effective_status
