"""J20 payment and webhook invariants for Nanovia Pro Pilot.

Every test uses a dedicated SQLite database and replaces Stripe boundaries with
local deterministic data. No provider network call is permitted from this file.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import stripe
from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.config import settings
from api.core.monetization import webhook_handler_service
from api.core.monetization.webhook_handler_service import (
    handle_stripe_webhook,
)
from api.database import Base
from api.models.pilot import PilotPayment, PilotRequest
from api.models.webhook_event import WebhookEvent
from api.routers import billing as billing_router
from api.services import billing_service, pilot_payment_service
from api.services.billing_service import (
    WEBHOOK_CLAIMED,
    WEBHOOK_IN_PROGRESS,
    claim_webhook_event,
)


PAYMENT_LINK_ID = "plink_pilot"
PRICE_ID = "price_pilot_297_cad"
PRODUCT_ID = "prod_pilot"


@pytest.fixture(autouse=True)
def _pilot_settings(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(settings, "STRIPE_PILOT_PAYMENT_LINK_ID", PAYMENT_LINK_ID)
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRICE_ID", PRICE_ID)
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRODUCT_ID", PRODUCT_ID)


@asynccontextmanager
async def _isolated_database(tmp_path: Path, name: str):
    database_path = (tmp_path / f"{name}.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                PilotRequest.__table__,
                PilotPayment.__table__,
                WebhookEvent.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


def _valid_session(
    *,
    session_id: str = "cs_pilot",
    payment_intent_id: str = "pi_pilot",
    request_id: uuid.UUID | str | None = None,
    email: str = "client@example.com",
    payment_status: str = "paid",
) -> dict:
    session = {
        "id": session_id,
        "mode": "payment",
        "livemode": False,
        "currency": "cad",
        "payment_link": PAYMENT_LINK_ID,
        "payment_intent": payment_intent_id,
        "payment_status": payment_status,
        "customer_details": {"email": email},
    }
    if request_id is not None:
        session["client_reference_id"] = str(request_id)
    return session


def _line_items(
    *,
    price_id: str = PRICE_ID,
    product_id: str = PRODUCT_ID,
    currency: str = "cad",
    recurring=None,
    price_type: str = "one_time",
    quantity: int = 1,
) -> dict:
    return {
        "data": [
            {
                "quantity": quantity,
                "amount_subtotal": 29700,
                "price": {
                    "id": price_id,
                    "currency": currency,
                    "recurring": recurring,
                    "type": price_type,
                    "product": product_id,
                },
            }
        ]
    }


def _install_line_items(monkeypatch, **overrides) -> AsyncMock:
    boundary = AsyncMock(return_value=_line_items(**overrides))
    monkeypatch.setattr(
        pilot_payment_service,
        "retrieve_pilot_line_items",
        boundary,
    )
    return boundary


def _request(body: bytes = b"{}") -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/billing/webhook",
            "headers": [],
        },
        receive,
    )


async def _add_request(
    db,
    *,
    email: str = "client@example.com",
    status: str = "pending",
    name: str = "Client Pilot",
) -> PilotRequest:
    request = PilotRequest(
        name=name,
        email=email,
        subject="demo",
        message="Automatiser une tâche répétitive.",
        status=status,
        notification_status="sent",
    )
    db.add(request)
    await db.commit()
    return request


def _existing_payment(
    *,
    request: PilotRequest,
    session_id: str,
    payment_intent_id: str,
    status: str = "paid",
) -> PilotPayment:
    return PilotPayment(
        pilot_request_id=request.id,
        stripe_checkout_session_id=session_id,
        stripe_payment_intent_id=payment_intent_id,
        stripe_event_id="evt_original",
        stripe_payment_link_id=PAYMENT_LINK_ID,
        stripe_price_id=PRICE_ID,
        customer_email=request.email,
        currency="cad",
        amount_subtotal=29700,
        payment_status="paid",
        status=status,
        livemode=False,
    )


@pytest.mark.asyncio
async def test_invalid_stripe_signature_returns_400(monkeypatch):
    def reject_signature(**_kwargs):
        raise stripe.error.SignatureVerificationError("invalid", "bad-signature")

    monkeypatch.setattr(
        billing_router.stripe.Webhook,
        "construct_event",
        reject_signature,
    )

    with pytest.raises(HTTPException) as exc_info:
        await billing_router.stripe_webhook(
            _request(),
            AsyncMock(),
            stripe_signature="bad-signature",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid Stripe signature"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_ids", "incoming_link"),
    [
        pytest.param(("", "", ""), PAYMENT_LINK_ID, id="configuration-absent"),
        pytest.param(
            (PAYMENT_LINK_ID, "", PRODUCT_ID),
            PAYMENT_LINK_ID,
            id="configuration-partial",
        ),
        pytest.param(
            (PAYMENT_LINK_ID, PRICE_ID, PRODUCT_ID),
            "",
            id="incoming-link-empty",
        ),
        pytest.param(
            (PAYMENT_LINK_ID, PRICE_ID, PRODUCT_ID),
            "plink_other",
            id="different-payment-link",
        ),
    ],
)
async def test_non_pilot_checkout_never_enters_pilot_dispatch(
    monkeypatch,
    configured_ids,
    incoming_link,
):
    payment_link_id, price_id, product_id = configured_ids
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PAYMENT_LINK_ID",
        payment_link_id,
    )
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRICE_ID", price_id)
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRODUCT_ID", product_id)
    pilot_processor = AsyncMock(return_value="paid")
    legacy_processor = AsyncMock()
    monkeypatch.setattr(
        billing_service,
        "process_pilot_checkout_event",
        pilot_processor,
    )
    monkeypatch.setattr(
        billing_service,
        "handle_checkout_completed",
        legacy_processor,
    )
    db = AsyncMock()

    result = await billing_service.process_stripe_event(
        "checkout.session.completed",
        {"payment_link": incoming_link},
        db,
        event_id="evt_non_pilot",
    )

    assert result == "processed"
    pilot_processor.assert_not_awaited()
    legacy_processor.assert_awaited_once()


@pytest.mark.asyncio
async def test_only_matching_configured_payment_link_enters_pilot_dispatch(
    monkeypatch,
):
    pilot_processor = AsyncMock(return_value="paid")
    legacy_processor = AsyncMock()
    monkeypatch.setattr(
        billing_service,
        "process_pilot_checkout_event",
        pilot_processor,
    )
    monkeypatch.setattr(
        billing_service,
        "handle_checkout_completed",
        legacy_processor,
    )
    db = AsyncMock()
    payload = {"payment_link": {"id": PAYMENT_LINK_ID}}

    result = await billing_service.process_stripe_event(
        "checkout.session.completed",
        payload,
        db,
        event_id="evt_matching_pilot",
    )

    assert result == "paid"
    pilot_processor.assert_awaited_once_with(
        "evt_matching_pilot",
        "checkout.session.completed",
        payload,
        db,
    )
    legacy_processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_matching_pilot_event_never_falls_back_to_legacy(
    monkeypatch,
):
    pilot_processor = AsyncMock(return_value="ignored")
    legacy_processor = AsyncMock()
    monkeypatch.setattr(
        billing_service,
        "process_pilot_checkout_event",
        pilot_processor,
    )
    monkeypatch.setattr(
        billing_service,
        "handle_checkout_completed",
        legacy_processor,
    )

    result = await billing_service.process_stripe_event(
        "checkout.session.completed",
        {"payment_link": PAYMENT_LINK_ID},
        AsyncMock(),
        event_id="evt_rejected_pilot",
    )

    assert result == "ignored"
    pilot_processor.assert_awaited_once()
    legacy_processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_unrelated_event_is_ignored_without_pilot_side_effect(monkeypatch):
    pilot_processor = AsyncMock(return_value="paid")
    monkeypatch.setattr(
        billing_service,
        "process_pilot_checkout_event",
        pilot_processor,
    )

    result = await billing_service.process_stripe_event(
        "payment_intent.created",
        {},
        AsyncMock(),
        event_id="evt_unrelated",
    )

    assert result == "ignored"
    pilot_processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_unconfigured_async_pilot_event_is_ignored(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PILOT_PAYMENT_LINK_ID", "")
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRICE_ID", "")
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRODUCT_ID", "")
    pilot_processor = AsyncMock(return_value="paid")
    monkeypatch.setattr(
        billing_service,
        "process_pilot_checkout_event",
        pilot_processor,
    )

    result = await billing_service.process_stripe_event(
        "checkout.session.async_payment_succeeded",
        {"payment_link": PAYMENT_LINK_ID},
        AsyncMock(),
        event_id="evt_unconfigured_async",
    )

    assert result == "ignored"
    pilot_processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_link_price_and_request_id_persist_paid_payment(
    monkeypatch,
    tmp_path,
):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "valid_payment") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db)
            result = await pilot_payment_service.process_pilot_checkout_event(
                "evt_valid",
                "checkout.session.completed",
                _valid_session(request_id=pilot_request.id),
                db,
            )
            await db.commit()

            payment = (await db.execute(select(PilotPayment))).scalar_one()
            assert result == "paid"
            assert payment.pilot_request_id == pilot_request.id
            assert payment.stripe_event_id == "evt_valid"
            assert payment.stripe_payment_link_id == PAYMENT_LINK_ID
            assert payment.stripe_price_id == PRICE_ID
            assert payment.currency == "cad"
            assert payment.amount_subtotal == 29700
            assert pilot_request.status == "paid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wrong_field", "wrong_value"),
    [
        pytest.param("payment_link", "plink_wrong", id="wrong-link"),
        pytest.param("price", "price_wrong", id="wrong-price"),
    ],
)
async def test_wrong_payment_link_or_price_is_ignored(
    monkeypatch,
    tmp_path,
    wrong_field,
    wrong_value,
):
    price_id = wrong_value if wrong_field == "price" else PRICE_ID
    line_items = _install_line_items(monkeypatch, price_id=price_id)
    async with _isolated_database(tmp_path, f"wrong_{wrong_field}") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db)
            session = _valid_session(request_id=pilot_request.id)
            if wrong_field == "payment_link":
                session["payment_link"] = wrong_value

            result = await pilot_payment_service.process_pilot_checkout_event(
                f"evt_wrong_{wrong_field}",
                "checkout.session.completed",
                session,
                db,
            )
            await db.commit()

            payment_count = await db.scalar(
                select(func.count()).select_from(PilotPayment)
            )
            assert result == "ignored"
            assert payment_count == 0
            assert pilot_request.status == "pending"
            assert line_items.await_count == (0 if wrong_field == "payment_link" else 1)


@pytest.mark.asyncio
async def test_unique_open_email_is_safe_fallback(monkeypatch, tmp_path):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "email_fallback") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, email="client@example.com")
            result = await pilot_payment_service.process_pilot_checkout_event(
                "evt_email",
                "checkout.session.completed",
                _valid_session(email="CLIENT@example.com"),
                db,
            )
            await db.commit()

            payment = (await db.execute(select(PilotPayment))).scalar_one()
            assert result == "paid"
            assert payment.pilot_request_id == pilot_request.id
            assert pilot_request.status == "paid"


@pytest.mark.asyncio
async def test_ambiguous_email_requires_manual_review(monkeypatch, tmp_path):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "email_ambiguous") as sessions:
        async with sessions() as db:
            first = await _add_request(db, name="Premier client")
            second = await _add_request(db, name="Deuxième client")

            result = await pilot_payment_service.process_pilot_checkout_event(
                "evt_ambiguous",
                "checkout.session.completed",
                _valid_session(),
                db,
            )
            await db.commit()

            payment = (await db.execute(select(PilotPayment))).scalar_one()
            assert result == "manual_review"
            assert payment.status == "manual_review"
            assert payment.pilot_request_id is None
            assert first.status == "pending"
            assert second.status == "pending"


@pytest.mark.asyncio
async def test_deferred_payment_transitions_processing_to_paid(monkeypatch, tmp_path):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "deferred_payment") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db)
            pending_session = _valid_session(
                request_id=pilot_request.id,
                payment_status="unpaid",
            )
            pending_result = await pilot_payment_service.process_pilot_checkout_event(
                "evt_deferred",
                "checkout.session.completed",
                pending_session,
                db,
            )
            await db.commit()

            paid_session = dict(pending_session, payment_status="paid")
            paid_result = await pilot_payment_service.process_pilot_checkout_event(
                "evt_deferred_paid",
                "checkout.session.async_payment_succeeded",
                paid_session,
                db,
            )
            await db.commit()

            payments = list((await db.execute(select(PilotPayment))).scalars())
            assert pending_result == "processing"
            assert paid_result == "paid"
            assert len(payments) == 1
            assert payments[0].status == "paid"
            assert payments[0].stripe_event_id == "evt_deferred_paid"
            assert pilot_request.status == "paid"


@pytest.mark.asyncio
async def test_duplicate_event_is_acknowledged_without_second_payment(
    monkeypatch,
    tmp_path,
):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "duplicate_event") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db)
            payload = _valid_session(request_id=pilot_request.id)

            first = await handle_stripe_webhook(
                "evt_duplicate",
                "checkout.session.completed",
                payload,
                db,
            )
            duplicate = await handle_stripe_webhook(
                "evt_duplicate",
                "checkout.session.completed",
                payload,
                db,
            )

            payment_count = await db.scalar(
                select(func.count()).select_from(PilotPayment)
            )
            event_count = await db.scalar(
                select(func.count()).select_from(WebhookEvent)
            )
            assert first["status"] == "paid"
            assert duplicate["status"] == "duplicate"
            assert payment_count == 1
            assert event_count == 1


@pytest.mark.asyncio
async def test_two_event_ids_for_same_session_keep_one_payment(
    monkeypatch,
    tmp_path,
):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "same_session") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db)
            payload = _valid_session(request_id=pilot_request.id)

            first = await handle_stripe_webhook(
                "evt_session_first",
                "checkout.session.completed",
                payload,
                db,
            )
            second = await handle_stripe_webhook(
                "evt_session_second",
                "checkout.session.async_payment_succeeded",
                payload,
                db,
            )

            payment_count = await db.scalar(
                select(func.count()).select_from(PilotPayment)
            )
            events = list(
                (
                    await db.execute(
                        select(WebhookEvent).order_by(WebhookEvent.stripe_event_id)
                    )
                ).scalars()
            )
            assert first["status"] == "paid"
            assert second["status"] == "duplicate"
            assert payment_count == 1
            assert len(events) == 2
            assert all(event.status == "processed" for event in events)


@pytest.mark.asyncio
async def test_database_failure_returns_503_then_retry_succeeds(
    monkeypatch,
    tmp_path,
):
    processor = AsyncMock(
        side_effect=[
            OperationalError(
                "UPDATE pilot_payments",
                {},
                RuntimeError("database temporarily unavailable"),
            ),
            "processed",
        ]
    )
    monkeypatch.setattr(
        webhook_handler_service,
        "process_stripe_event",
        processor,
    )
    event = {
        "id": "evt_retry",
        "type": "invoice.payment_succeeded",
        "data": {"object": {"id": "in_retry"}},
    }
    monkeypatch.setattr(
        billing_router.stripe.Webhook,
        "construct_event",
        lambda **_kwargs: event,
    )

    async with _isolated_database(tmp_path, "retry") as sessions:
        async with sessions() as db:
            with pytest.raises(HTTPException) as exc_info:
                await billing_router.stripe_webhook(
                    _request(),
                    db,
                    stripe_signature="valid-local-signature",
                )
            assert exc_info.value.status_code == 503

            retryable = (
                await db.execute(
                    select(WebhookEvent).where(
                        WebhookEvent.stripe_event_id == "evt_retry"
                    )
                )
            ).scalar_one()
            assert retryable.status == "retryable_failure"
            assert retryable.attempt_count == 1

            response = await billing_router.stripe_webhook(
                _request(),
                db,
                stripe_signature="valid-local-signature",
            )
            await db.refresh(retryable)

            assert response == {
                "received": True,
                "status": "processed",
                "type": "invoice.payment_succeeded",
            }
            assert retryable.status == "processed"
            assert retryable.attempt_count == 2
            assert processor.await_count == 2
            assert all(
                call.kwargs["event_id"] == "evt_retry"
                for call in processor.await_args_list
            )


@pytest.mark.asyncio
async def test_checkout_session_collision_requires_manual_review(
    monkeypatch,
    tmp_path,
):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "session_collision") as sessions:
        async with sessions() as db:
            original_request = await _add_request(db, name="Client original")
            current_request = await _add_request(
                db,
                email="current@example.com",
                name="Client actuel",
            )
            payment = _existing_payment(
                request=original_request,
                session_id="cs_collision",
                payment_intent_id="pi_original",
            )
            db.add(payment)
            await db.commit()

            result = await pilot_payment_service.process_pilot_checkout_event(
                "evt_session_collision",
                "checkout.session.completed",
                _valid_session(
                    session_id="cs_collision",
                    payment_intent_id="pi_different",
                    request_id=current_request.id,
                    email=current_request.email,
                ),
                db,
            )
            await db.commit()

            assert result == "manual_review"
            assert payment.status == "manual_review"
            assert original_request.status == "manual_review"
            assert current_request.status == "manual_review"


@pytest.mark.asyncio
async def test_payment_intent_collision_requires_manual_review(
    monkeypatch,
    tmp_path,
):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "intent_collision") as sessions:
        async with sessions() as db:
            original_request = await _add_request(db, name="Client original")
            current_request = await _add_request(
                db,
                email="current@example.com",
                name="Client actuel",
            )
            payment = _existing_payment(
                request=original_request,
                session_id="cs_original",
                payment_intent_id="pi_collision",
            )
            db.add(payment)
            await db.commit()

            result = await pilot_payment_service.process_pilot_checkout_event(
                "evt_intent_collision",
                "checkout.session.completed",
                _valid_session(
                    session_id="cs_different",
                    payment_intent_id="pi_collision",
                    request_id=current_request.id,
                    email=current_request.email,
                ),
                db,
            )
            await db.commit()

            payment_count = await db.scalar(
                select(func.count()).select_from(PilotPayment)
            )
            assert result == "manual_review"
            assert payment_count == 1
            assert payment.status == "manual_review"
            assert original_request.status == "manual_review"
            assert current_request.status == "manual_review"


@pytest.mark.asyncio
async def test_atomic_claim_prevents_second_worker_from_processing(
    tmp_path,
):
    async with _isolated_database(tmp_path, "atomic_claim") as sessions:
        async with sessions() as first_db:
            first_claim = await claim_webhook_event(
                "evt_atomic",
                "checkout.session.completed",
                first_db,
            )
            await first_db.commit()

        async with sessions() as second_db:
            second_claim = await claim_webhook_event(
                "evt_atomic",
                "checkout.session.completed",
                second_db,
            )
            event_count = await second_db.scalar(
                select(func.count()).select_from(WebhookEvent)
            )
            await second_db.rollback()

        assert first_claim == WEBHOOK_CLAIMED
        assert second_claim == WEBHOOK_IN_PROGRESS
        assert event_count == 1
