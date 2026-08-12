"""J20 payment and webhook invariants for Nanovia Pro Pilot.

Every test uses a dedicated SQLite database and replaces Stripe boundaries with
local deterministic data. No provider network call is permitted from this file.
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import stripe
from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.config import settings
from api.core.monetization import webhook_handler_service
from api.core.monetization.webhook_handler_service import (
    handle_stripe_webhook,
)
from api.database import Base
from api.models.audit import AuditLog
from api.models.credit_ledger import CreditLedger
from api.models.pilot import PilotPayment, PilotRequest
from api.models.user import User
from api.models.user_module import UserModule
from api.models.webhook_event import WebhookEvent
from api.routers import admin as admin_router
from api.routers import billing as billing_router
from api.services import (
    billing_service,
    credit_service,
    pilot_payment_service,
    pilot_stripe_contract_service,
)
from api.services.billing_service import (
    WEBHOOK_CLAIMED,
    WEBHOOK_IN_PROGRESS,
    claim_webhook_event,
)
from api.services.pilot_stripe_contract_service import (
    PILOT_CONTRACT_MARKER,
    PilotStripeContractError,
    validate_pilot_checkout,
)


ACCOUNT_ID = "acct_pilot"
PAYMENT_LINK_ID = "plink_pilot"
PAYMENT_LINK_URL = "https://buy.stripe.com/test_pilot"
PRICE_ID = "price_pilot297cad"
PRODUCT_ID = "prod_pilot"
CREDIT_PRICE_ID = "price_credit_pack"
CREDIT_OLD_PRICE_ID = "price_credit_pack_previous"
CREDIT_PRODUCT_ID = "prod_credit_pack"
CREDIT_PACK_SIZE = 25
CREDIT_UNIT_AMOUNT = 400
CREDIT_OLD_PRICE_CREATED = 1_700_000_000
CREDIT_CURRENT_PRICE_CREATED = 1_700_001_000
PREVIOUS_PAYMENT_LINK_ID = "plink_previousPilot"
PREVIOUS_PAYMENT_LINK_URL = "https://buy.stripe.com/previousPilot"
PREVIOUS_PRICE_ID = "price_previousPilot"
PREVIOUS_PRODUCT_ID = "prod_previousPilot"

_REAL_VERIFY_CREDIT_CHECKOUT = billing_service.verify_credit_checkout_session


def _previous_pilot_contract_json(
    *,
    product_id: str = PREVIOUS_PRODUCT_ID,
    price_id: str = PREVIOUS_PRICE_ID,
    payment_link_id: str = PREVIOUS_PAYMENT_LINK_ID,
    payment_link_url: str = PREVIOUS_PAYMENT_LINK_URL,
) -> str:
    return json.dumps(
        [
            {
                "product_id": product_id,
                "price_id": price_id,
                "payment_link_id": payment_link_id,
                "payment_link_url": payment_link_url,
            }
        ]
    )


@pytest.fixture(autouse=True)
def _pilot_settings(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(settings, "STRIPE_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setattr(settings, "STRIPE_PILOT_PAYMENT_LINK_ID", PAYMENT_LINK_ID)
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PAYMENT_LINK_URL",
        PAYMENT_LINK_URL,
    )
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRICE_ID", PRICE_ID)
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRODUCT_ID", PRODUCT_ID)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_local_test")
    monkeypatch.setattr(settings, "STRIPE_CREDIT_PRICE_ID", CREDIT_PRICE_ID)
    monkeypatch.setattr(settings, "STRIPE_CREDIT_PACK_SIZE", CREDIT_PACK_SIZE)
    monkeypatch.setattr(settings, "STRIPE_CREDIT_UNIT_AMOUNT", CREDIT_UNIT_AMOUNT)
    monkeypatch.setattr(settings, "STRIPE_CREDIT_CURRENCY", "usd")
    monkeypatch.setattr(settings, "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON", "[]")
    monkeypatch.setattr(
        billing_service,
        "retrieve_credit_line_items",
        AsyncMock(return_value=_credit_line_items()),
    )

    async def verify_credit(event_id, signed_session):
        return billing_service.validate_credit_checkout_contract(
            signed_session,
            event_id=event_id,
            provider_event=_credit_event(event_id, signed_session),
            provider_session=_credit_provider_session(signed_session),
            account=_credit_account(),
            customer=_credit_customer(signed_session),
            line_items_response=await billing_service.retrieve_credit_line_items(
                signed_session["id"]
            ),
            current_price=_credit_price(),
        )

    monkeypatch.setattr(
        billing_service,
        "verify_credit_checkout_session",
        AsyncMock(side_effect=verify_credit),
    )
    _install_line_items(monkeypatch)


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


@asynccontextmanager
async def _isolated_legacy_database(tmp_path: Path, name: str):
    database_path = (tmp_path / f"{name}.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                User.__table__,
                CreditLedger.__table__,
                AuditLog.__table__,
                UserModule.__table__,
                WebhookEvent.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


def _legacy_credit_checkout(
    user_id: uuid.UUID,
    *,
    session_id: str,
    payment_status: str = "paid",
    credits: object = CREDIT_PACK_SIZE,
    amount_total: object = CREDIT_UNIT_AMOUNT,
    created: int = CREDIT_CURRENT_PRICE_CREATED + 100,
) -> dict:
    return {
        "id": session_id,
        "mode": "payment",
        "status": "complete" if payment_status == "paid" else "open",
        "payment_status": payment_status,
        "payment_intent": f"pi_{session_id.removeprefix('cs_')}",
        "livemode": False,
        "currency": "usd",
        "created": created,
        "amount_subtotal": amount_total,
        "amount_total": amount_total,
        "total_details": {
            "amount_discount": 0,
            "amount_tax": 0,
            "amount_shipping": 0,
        },
        "customer": "cus_legacy",
        "client_reference_id": str(user_id),
        "metadata": {
            "type": "credits",
            "user_id": str(user_id),
            "credits": str(credits),
        },
    }


def _credit_product(*, product_id: str = CREDIT_PRODUCT_ID) -> dict:
    return {
        "id": product_id,
        "active": True,
        "livemode": False,
        "metadata": {
            "product_key": "credit_pack",
            "credits": str(CREDIT_PACK_SIZE),
        },
    }


def _credit_price(
    *,
    price_id: str = CREDIT_PRICE_ID,
    created: int = CREDIT_CURRENT_PRICE_CREATED,
    active: bool = True,
    currency: str = "usd",
    unit_amount: int = CREDIT_UNIT_AMOUNT,
    product_id: str = CREDIT_PRODUCT_ID,
) -> dict:
    return {
        "id": price_id,
        "active": active,
        "livemode": False,
        "created": created,
        "unit_amount": unit_amount,
        "currency": currency,
        "type": "one_time",
        "recurring": None,
        "metadata": {
            "product_key": "credit_pack",
            "credits": str(CREDIT_PACK_SIZE),
        },
        "product": _credit_product(product_id=product_id),
    }


def _credit_line_items(
    *,
    price_id: str = CREDIT_PRICE_ID,
    price_created: int = CREDIT_CURRENT_PRICE_CREATED,
    price_active: bool = True,
    currency: str = "usd",
    unit_amount: int = CREDIT_UNIT_AMOUNT,
    quantity: int = 1,
    product_id: str = CREDIT_PRODUCT_ID,
) -> dict:
    amount = unit_amount * quantity
    return {
        "data": [
            {
                "quantity": quantity,
                "amount_subtotal": amount,
                "amount_total": amount,
                "price": _credit_price(
                    price_id=price_id,
                    created=price_created,
                    active=price_active,
                    currency=currency,
                    unit_amount=unit_amount,
                    product_id=product_id,
                ),
            }
        ]
    }


def _credit_account(*, account_id: str = ACCOUNT_ID) -> dict:
    return {
        "id": account_id,
        "charges_enabled": True,
        "details_submitted": True,
    }


def _credit_event(event_id: str, signed_session: dict) -> dict:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "livemode": False,
        "account": ACCOUNT_ID,
        "data": {"object": deepcopy(signed_session)},
    }


def _credit_customer(signed_session: dict, *, user_id: object | None = None) -> dict:
    owner_id = user_id or signed_session.get("client_reference_id")
    return {
        "id": signed_session.get("customer"),
        "livemode": False,
        "metadata": {
            "user_id": str(owner_id),
            "app": settings.APP_NAME,
        },
    }


def _credit_provider_session(signed_session: dict) -> dict:
    provider = deepcopy(signed_session)
    paid = provider.get("payment_status") == "paid"
    provider["payment_intent"] = {
        "id": signed_session.get("payment_intent"),
        "livemode": False,
        "status": "succeeded" if paid else "processing",
        "currency": provider.get("currency"),
        "amount": provider.get("amount_total"),
        "amount_received": provider.get("amount_total") if paid else 0,
        "customer": provider.get("customer"),
    }
    return provider


def _install_credit_provider_contract(
    monkeypatch,
    signed_session: dict,
    *,
    event_id: str,
    provider_event: dict | None = None,
    provider_session: dict | None = None,
    account: dict | None = None,
    customer: dict | None = None,
    line_items: dict | None = None,
    current_price: dict | None = None,
) -> dict[str, AsyncMock]:
    async def retrieve_event(requested_event_id):
        if provider_event is not None:
            return provider_event
        return _credit_event(requested_event_id, signed_session)

    boundaries = {
        "event": AsyncMock(side_effect=retrieve_event),
        "session": AsyncMock(
            return_value=provider_session or _credit_provider_session(signed_session)
        ),
        "account": AsyncMock(return_value=account or _credit_account()),
        "customer": AsyncMock(return_value=customer or _credit_customer(signed_session)),
        "line_items": AsyncMock(return_value=line_items or _credit_line_items()),
        "price": AsyncMock(return_value=current_price or _credit_price()),
    }
    monkeypatch.setattr(
        billing_service,
        "verify_credit_checkout_session",
        _REAL_VERIFY_CREDIT_CHECKOUT,
    )
    monkeypatch.setattr(billing_service, "retrieve_credit_event", boundaries["event"])
    monkeypatch.setattr(
        billing_service,
        "retrieve_credit_checkout_session",
        boundaries["session"],
    )
    monkeypatch.setattr(billing_service, "retrieve_credit_account", boundaries["account"])
    monkeypatch.setattr(
        billing_service,
        "retrieve_credit_customer",
        boundaries["customer"],
    )
    monkeypatch.setattr(
        billing_service,
        "retrieve_credit_line_items",
        boundaries["line_items"],
    )
    monkeypatch.setattr(billing_service, "retrieve_credit_price", boundaries["price"])
    return boundaries


def _legacy_module_checkout(user_id: uuid.UUID, *, session_id: str) -> dict:
    return {
        "id": session_id,
        "mode": "subscription",
        "payment_status": "paid",
        "customer": "cus_legacy_module",
        "subscription": "sub_legacy_module",
        "client_reference_id": str(user_id),
        "metadata": {"type": "module", "module": "operator"},
    }


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
        "amount_subtotal": 29700,
        "amount_total": 29700,
        "payment_link": PAYMENT_LINK_ID,
        "payment_intent": payment_intent_id,
        "payment_status": payment_status,
        "customer": "cus_pilot",
        "customer_details": {"email": email},
        "metadata": {"nanovia_contract": PILOT_CONTRACT_MARKER},
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
    unit_amount: int = 29700,
    price_active: bool = True,
    product_active: bool = True,
) -> dict:
    return {
        "data": [
            {
                "quantity": quantity,
                "amount_subtotal": 29700,
                "amount_total": 29700,
                "price": {
                    "id": price_id,
                    "active": price_active,
                    "livemode": False,
                    "unit_amount": unit_amount,
                    "currency": currency,
                    "recurring": recurring,
                    "type": price_type,
                    "product": {
                        "id": product_id,
                        "active": product_active,
                        "livemode": False,
                        "name": "Nanovia Pro Pilot",
                        "metadata": {
                            "nanovia_contract": PILOT_CONTRACT_MARKER,
                        },
                    },
                },
            }
        ]
    }


def _provider_session(signed_session: dict) -> dict:
    payment_status = signed_session.get("payment_status", "paid")
    paid = payment_status == "paid"
    payment_intent_id = signed_session.get("payment_intent", "pi_pilot")
    customer_id = signed_session.get("customer", "cus_pilot")
    provider = dict(signed_session)
    provider.update(
        {
            "status": "complete" if paid else "open",
            "amount_subtotal": signed_session.get("amount_subtotal", 29700),
            "amount_total": signed_session.get("amount_total", 29700),
            "total_details": {
                "amount_discount": 0,
                "amount_tax": 0,
                "amount_shipping": 0,
            },
            "discounts": [],
            "customer": customer_id,
            "metadata": {"nanovia_contract": PILOT_CONTRACT_MARKER},
            "payment_intent": {
                "id": payment_intent_id,
                "livemode": False,
                "amount": 29700,
                "amount_received": 29700 if paid else 0,
                "currency": "cad",
                "customer": customer_id,
                "status": "succeeded" if paid else "processing",
                "latest_charge": {
                    "id": "ch_pilot",
                    "livemode": False,
                    "paid": paid,
                    "refunded": False,
                    "disputed": False,
                    "amount": 29700,
                    "amount_captured": 29700 if paid else 0,
                    "amount_refunded": 0,
                    "currency": "cad",
                    "customer": customer_id,
                    "balance_transaction": {
                        "id": "txn_pilot",
                        "amount": 29700,
                        "currency": "cad",
                        "fee": 1174,
                        "net": 28526,
                    },
                },
            },
        }
    )
    return provider


def _install_line_items(monkeypatch, **overrides) -> AsyncMock:
    async def verify(event_id, event_type, signed_session):
        del event_id
        provider_session = _provider_session(signed_session)
        config = pilot_stripe_contract_service.load_pilot_stripe_config()
        require_paid = event_type == "checkout.session.async_payment_succeeded" or (
            event_type == "checkout.session.completed"
            and provider_session.get("payment_status") == "paid"
        )
        return validate_pilot_checkout(
            provider_session,
            _line_items(**overrides),
            config,
            require_paid=require_paid,
        )

    boundary = AsyncMock(side_effect=verify)
    monkeypatch.setattr(
        pilot_payment_service,
        "verify_pilot_checkout_event",
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
    payment_status: str = "paid",
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
        payment_status=payment_status,
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
async def test_webhook_signature_uses_bounded_tolerance_and_server_secret(monkeypatch):
    captured = {}

    def construct_event(**kwargs):
        captured.update(kwargs)
        return {
            "id": "evt_signature_contract",
            "type": "payment_intent.created",
            "data": {"object": {"id": "pi_signature_contract"}},
        }

    handler = AsyncMock(
        return_value={
            "event_id": "evt_signature_contract",
            "event_type": "payment_intent.created",
            "status": "ignored",
        }
    )
    monkeypatch.setattr(
        billing_router.stripe.Webhook,
        "construct_event",
        construct_event,
    )
    monkeypatch.setattr(billing_router, "handle_stripe_webhook", handler)

    response = await billing_router.stripe_webhook(
        _request(b'{"synthetic":true}'),
        AsyncMock(),
        stripe_signature="t=123,v1=synthetic",
    )

    assert captured["secret"] == "whsec_local_test"
    assert captured["tolerance"] == 300
    assert captured["payload"] == b'{"synthetic":true}'
    assert response["status"] == "ignored"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_webhook_secret_fails_before_signature_processing(monkeypatch):
    construct_event = AsyncMock(
        side_effect=AssertionError("Missing secret must fail before Stripe")
    )
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(
        billing_router.stripe.Webhook,
        "construct_event",
        construct_event,
    )

    with pytest.raises(HTTPException) as exc_info:
        await billing_router.stripe_webhook(
            _request(),
            AsyncMock(),
            stripe_signature="t=123,v1=synthetic",
        )

    assert exc_info.value.status_code == 503
    construct_event.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_ids", "incoming_link", "expected"),
    [
        pytest.param(
            ("", "", ""),
            PAYMENT_LINK_ID,
            "legacy",
            id="configuration-absent",
        ),
        pytest.param(
            (PAYMENT_LINK_ID, "", PRODUCT_ID),
            PAYMENT_LINK_ID,
            "configuration_error",
            id="configuration-partial",
        ),
        pytest.param(
            (PAYMENT_LINK_ID, PRICE_ID, PRODUCT_ID),
            "",
            "legacy",
            id="incoming-link-empty",
        ),
        pytest.param(
            (PAYMENT_LINK_ID, PRICE_ID, PRODUCT_ID),
            "plink_other",
            "ignored",
            id="different-payment-link",
        ),
    ],
)
async def test_non_pilot_checkout_never_enters_pilot_dispatch(
    monkeypatch,
    configured_ids,
    incoming_link,
    expected,
):
    payment_link_id, price_id, product_id = configured_ids
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PAYMENT_LINK_ID",
        payment_link_id,
    )
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRICE_ID", price_id)
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRODUCT_ID", product_id)
    if not any(configured_ids):
        monkeypatch.setattr(settings, "STRIPE_PILOT_PAYMENT_LINK_URL", "")
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

    if expected == "configuration_error":
        with pytest.raises(PilotStripeContractError):
            await billing_service.process_stripe_event(
                "checkout.session.completed",
                {"payment_link": incoming_link},
                db,
                event_id="evt_non_pilot",
            )
    else:
        result = await billing_service.process_stripe_event(
            "checkout.session.completed",
            {"payment_link": incoming_link},
            db,
            event_id="evt_non_pilot",
        )
        assert result == ("processed" if expected == "legacy" else "ignored")
    pilot_processor.assert_not_awaited()
    if expected == "legacy":
        legacy_processor.assert_awaited_once()
    else:
        legacy_processor.assert_not_awaited()


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
async def test_unconfigured_async_pilot_event_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PILOT_PAYMENT_LINK_ID", "")
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRICE_ID", "")
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRODUCT_ID", "")
    pilot_processor = AsyncMock(return_value="paid")
    monkeypatch.setattr(
        billing_service,
        "process_pilot_checkout_event",
        pilot_processor,
    )

    with pytest.raises(PilotStripeContractError):
        await billing_service.process_stripe_event(
            "checkout.session.async_payment_succeeded",
            {"payment_link": PAYMENT_LINK_ID},
            AsyncMock(),
            event_id="evt_unconfigured_async",
        )
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
async def test_paid_checkout_from_explicit_previous_contract_replays_once(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON",
        _previous_pilot_contract_json(),
    )

    async def verify(event_id, event_type, signed_session):
        del event_id
        provider_session = _provider_session(signed_session)
        config = pilot_stripe_contract_service.find_authorized_pilot_stripe_config(
            signed_session["payment_link"]
        )
        assert config is not None
        require_paid = event_type == "checkout.session.async_payment_succeeded" or (
            event_type == "checkout.session.completed"
            and provider_session.get("payment_status") == "paid"
        )
        return validate_pilot_checkout(
            provider_session,
            _line_items(
                price_id=PREVIOUS_PRICE_ID,
                product_id=PREVIOUS_PRODUCT_ID,
                price_active=False,
                product_active=False,
            ),
            config,
            require_paid=require_paid,
        )

    verifier = AsyncMock(side_effect=verify)
    monkeypatch.setattr(
        pilot_payment_service,
        "verify_pilot_checkout_event",
        verifier,
    )
    async with _isolated_database(tmp_path, "previous_pilot_payment") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db)
            payload = _valid_session(
                request_id=pilot_request.id,
                session_id="cs_previous_pilot",
                payment_intent_id="pi_previous_pilot",
            )
            payload["payment_link"] = PREVIOUS_PAYMENT_LINK_ID

            first = await handle_stripe_webhook(
                "evt_previous_pilot",
                "checkout.session.completed",
                payload,
                db,
            )
            duplicate = await handle_stripe_webhook(
                "evt_previous_pilot",
                "checkout.session.completed",
                payload,
                db,
            )
            distinct = await handle_stripe_webhook(
                "evt_previous_pilot_distinct",
                "checkout.session.completed",
                payload,
                db,
            )

            payment = (await db.execute(select(PilotPayment))).scalar_one()
            events = list((await db.execute(select(WebhookEvent))).scalars())
            assert first["status"] == "paid"
            assert duplicate["status"] == "duplicate"
            assert distinct["status"] == "duplicate"
            assert payment.stripe_payment_link_id == PREVIOUS_PAYMENT_LINK_ID
            assert payment.stripe_price_id == PREVIOUS_PRICE_ID
            assert payment.status == "paid"
            assert pilot_request.status == "paid"
            assert len(events) == 2
            assert all(event.status == "processed" for event in events)
            assert verifier.await_count == 2


@pytest.mark.asyncio
async def test_unverifiable_previous_contract_stays_retryable_without_effect(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON",
        _previous_pilot_contract_json(),
    )
    verifier = AsyncMock(
        side_effect=pilot_stripe_contract_service.PilotStripeProviderUnavailable(
            "local provider outage"
        )
    )
    monkeypatch.setattr(
        pilot_payment_service,
        "verify_pilot_checkout_event",
        verifier,
    )
    async with _isolated_database(tmp_path, "previous_pilot_retryable") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db)
            pilot_request_id = pilot_request.id
            payload = _valid_session(request_id=pilot_request.id)
            payload["payment_link"] = PREVIOUS_PAYMENT_LINK_ID

            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    "evt_previous_retryable",
                    "checkout.session.completed",
                    payload,
                    db,
                )

            event = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_previous_retryable"
                )
            )
            assert event is not None and event.status == "retryable_failure"
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 0
            persisted_request = await db.get(PilotRequest, pilot_request_id)
            assert persisted_request is not None and persisted_request.status == "pending"


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

            if wrong_field == "price":
                with pytest.raises(PilotStripeContractError):
                    await pilot_payment_service.process_pilot_checkout_event(
                        f"evt_wrong_{wrong_field}",
                        "checkout.session.completed",
                        session,
                        db,
                    )
                result = "ignored"
            else:
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
async def test_unique_open_email_without_request_reference_is_rejected(
    monkeypatch,
    tmp_path,
):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "email_fallback") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, email="client@example.com")
            with pytest.raises(PilotStripeContractError):
                await pilot_payment_service.process_pilot_checkout_event(
                    "evt_email",
                    "checkout.session.completed",
                    _valid_session(email="CLIENT@example.com"),
                    db,
                )
            await db.commit()

            payment_count = await db.scalar(
                select(func.count()).select_from(PilotPayment)
            )
            assert payment_count == 0
            assert pilot_request.status == "pending"


@pytest.mark.asyncio
async def test_ambiguous_email_requires_manual_review(monkeypatch, tmp_path):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "email_ambiguous") as sessions:
        async with sessions() as db:
            first = await _add_request(db, name="Premier client")
            second = await _add_request(db, name="Deuxième client")

            with pytest.raises(PilotStripeContractError):
                await pilot_payment_service.process_pilot_checkout_event(
                    "evt_ambiguous",
                    "checkout.session.completed",
                    _valid_session(),
                    db,
                )
            await db.commit()

            payment_count = await db.scalar(
                select(func.count()).select_from(PilotPayment)
            )
            assert payment_count == 0
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
async def test_paid_retry_after_failed_checkout_confirms_once(monkeypatch, tmp_path):
    _install_line_items(monkeypatch)
    async with _isolated_database(tmp_path, "failed_checkout_retry") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db)
            failed_session = _valid_session(
                session_id="cs_failed_attempt",
                payment_intent_id="pi_failed_attempt",
                request_id=pilot_request.id,
                payment_status="unpaid",
            )
            paid_session = _valid_session(
                session_id="cs_paid_retry",
                payment_intent_id="pi_paid_retry",
                request_id=pilot_request.id,
            )

            failed = await handle_stripe_webhook(
                "evt_failed_attempt",
                "checkout.session.async_payment_failed",
                failed_session,
                db,
            )
            paid = await handle_stripe_webhook(
                "evt_paid_retry",
                "checkout.session.completed",
                paid_session,
                db,
            )
            repeated_paid = await handle_stripe_webhook(
                "evt_paid_retry",
                "checkout.session.completed",
                paid_session,
                db,
            )
            late_failed = await handle_stripe_webhook(
                "evt_failed_attempt_late",
                "checkout.session.async_payment_failed",
                failed_session,
                db,
            )

            verified_paid = validate_pilot_checkout(
                _provider_session(paid_session),
                _line_items(),
                pilot_stripe_contract_service.load_pilot_stripe_config(),
                require_paid=True,
            )
            provider_lookup = AsyncMock(return_value=verified_paid)
            monkeypatch.setattr(
                billing_router,
                "_retrieve_pilot_checkout_session",
                provider_lookup,
            )
            confirmed = await billing_router.get_pilot_confirmation(
                db,
                session_id="cs_paid_retry",
            )
            repeated_confirmation = await billing_router.get_pilot_confirmation(
                db,
                session_id="cs_paid_retry",
            )

            payments = {
                payment.stripe_checkout_session_id: payment
                for payment in (await db.execute(select(PilotPayment))).scalars()
            }
            events = list((await db.execute(select(WebhookEvent))).scalars())

            assert failed["status"] == "failed"
            assert paid["status"] == "paid"
            assert repeated_paid["status"] == "duplicate"
            assert late_failed["status"] == "duplicate"
            assert confirmed.model_dump() == {"status": "confirmed"}
            assert repeated_confirmation.model_dump() == {"status": "confirmed"}
            assert set(payments) == {"cs_failed_attempt", "cs_paid_retry"}
            assert payments["cs_failed_attempt"].status == "failed"
            assert payments["cs_failed_attempt"].payment_status == "unpaid"
            assert payments["cs_paid_retry"].status == "paid"
            assert payments["cs_paid_retry"].payment_status == "paid"
            assert sum(payment.status == "paid" for payment in payments.values()) == 1
            assert pilot_request.status == "paid"
            assert len(events) == 3
            assert all(event.status == "processed" for event in events)
            assert provider_lookup.await_count == 2


@pytest.mark.asyncio
async def test_terminal_event_for_obsolete_failed_attempt_preserves_paid_retry(
    monkeypatch,
    tmp_path,
):
    provider_object = _reversal_object("payment_intent.canceled")
    verifier = _install_reversal_verification(monkeypatch, provider_object)
    async with _isolated_database(tmp_path, "obsolete_failed_attempt") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status="paid")
            failed_attempt = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
                status="failed",
                payment_status="unpaid",
            )
            paid_retry = _existing_payment(
                request=pilot_request,
                session_id="cs_paid_retry",
                payment_intent_id="pi_paid_retry",
            )
            db.add_all([failed_attempt, paid_retry])
            await db.commit()

            first = await handle_stripe_webhook(
                "evt_obsolete_attempt_canceled",
                "payment_intent.canceled",
                provider_object,
                db,
            )
            duplicate = await handle_stripe_webhook(
                "evt_obsolete_attempt_canceled",
                "payment_intent.canceled",
                provider_object,
                db,
            )
            await db.refresh(failed_attempt)
            await db.refresh(paid_retry)
            await db.refresh(pilot_request)
            events = list((await db.execute(select(WebhookEvent))).scalars())

            assert first["status"] == "failed"
            assert duplicate["status"] == "duplicate"
            assert failed_attempt.status == "failed"
            assert failed_attempt.payment_status == "canceled"
            assert failed_attempt.stripe_event_id == "evt_obsolete_attempt_canceled"
            assert paid_retry.status == "paid"
            assert paid_retry.payment_status == "paid"
            assert pilot_request.status == "paid"
            assert len(events) == 1
            assert events[0].status == "processed"
            assert events[0].attempt_count == 1
            verifier.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_status", "existing_payment_status"),
    [
        pytest.param("paid", "paid", id="paid"),
        pytest.param("processing", "unpaid", id="processing"),
        pytest.param("manual_review", "unpaid", id="manual-review"),
        pytest.param("failed", "", id="ambiguous-failure"),
        pytest.param("failed", "refunded", id="refunded"),
        pytest.param("failed", "dispute_lost", id="dispute-lost"),
        pytest.param("failed", "canceled", id="canceled"),
    ],
)
async def test_paid_retry_does_not_supersede_non_retryable_attempt(
    monkeypatch,
    tmp_path,
    existing_status,
    existing_payment_status,
):
    _install_line_items(monkeypatch)
    async with _isolated_database(
        tmp_path,
        f"blocked_retry_{existing_status}_{existing_payment_status or 'empty'}",
    ) as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status=existing_status)
            original_payment = _existing_payment(
                request=pilot_request,
                session_id="cs_existing_attempt",
                payment_intent_id="pi_existing_attempt",
                status=existing_status,
                payment_status=existing_payment_status,
            )
            db.add(original_payment)
            await db.commit()

            result = await pilot_payment_service.process_pilot_checkout_event(
                "evt_blocked_retry",
                "checkout.session.completed",
                _valid_session(
                    session_id="cs_blocked_retry",
                    payment_intent_id="pi_blocked_retry",
                    request_id=pilot_request.id,
                ),
                db,
            )
            await db.commit()

            payments = list((await db.execute(select(PilotPayment))).scalars())
            expected_status = (
                "failed" if existing_status == "failed" else "manual_review"
            )
            assert result == "manual_review"
            assert len(payments) == 1
            assert payments[0].stripe_checkout_session_id == "cs_existing_attempt"
            assert original_payment.status == expected_status
            assert pilot_request.status == expected_status


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


def _reversal_object(
    event_type: str,
    *,
    amount: int = 29_700,
    status: str | None = None,
) -> dict:
    if event_type == "payment_intent.canceled":
        return {
            "id": "pi_reversal",
            "livemode": False,
            "currency": "cad",
            "status": "canceled",
        }
    value = {
        "id": "ch_reversal" if event_type == "charge.refunded" else "obj_reversal",
        "payment_intent": "pi_reversal",
        "livemode": False,
        "currency": "cad",
    }
    if event_type == "charge.refunded":
        value["amount_refunded"] = amount
    elif event_type.startswith("refund."):
        value["amount"] = amount
        value["status"] = status or "succeeded"
    elif event_type == "charge.dispute.closed":
        value["status"] = status or "lost"
    return value


def _reversal_session(
    *,
    payment_intent_id: str = "pi_reversal",
    payment_link_id: str = PAYMENT_LINK_ID,
    amount_total: int = 29_700,
) -> dict:
    return {
        "id": "cs_reversal",
        "payment_intent": payment_intent_id,
        "payment_link": payment_link_id,
        "mode": "payment",
        "livemode": False,
        "currency": "cad",
        "amount_subtotal": amount_total,
        "amount_total": amount_total,
        "metadata": {"nanovia_contract": PILOT_CONTRACT_MARKER},
    }


def _install_reversal_verification(monkeypatch, provider_object: dict) -> AsyncMock:
    boundary = AsyncMock(
        return_value=(
            provider_object,
            pilot_stripe_contract_service.load_pilot_stripe_config(),
        )
    )
    monkeypatch.setattr(
        pilot_payment_service,
        "verify_pilot_reversal_event",
        boundary,
    )
    monkeypatch.setattr(
        pilot_payment_service,
        "retrieve_pilot_reversal_sessions",
        AsyncMock(return_value={"data": [_reversal_session()]}),
    )
    return boundary


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "amount", "provider_status", "expected_status"),
    [
        pytest.param(
            "charge.refunded",
            29_700,
            None,
            "failed",
            id="full-refund",
        ),
        pytest.param(
            "charge.refunded",
            10_000,
            None,
            "manual_review",
            id="partial-refund",
        ),
        pytest.param(
            "refund.updated",
            29_700,
            "pending",
            "manual_review",
            id="pending-refund",
        ),
        pytest.param(
            "charge.dispute.created",
            29_700,
            None,
            "manual_review",
            id="dispute-created",
        ),
        pytest.param(
            "charge.dispute.closed",
            29_700,
            "lost",
            "failed",
            id="dispute-lost",
        ),
        pytest.param(
            "charge.dispute.closed",
            29_700,
            "won",
            "manual_review",
            id="dispute-won-no-reactivation",
        ),
        pytest.param(
            "payment_intent.canceled",
            29_700,
            None,
            "failed",
            id="payment-intent-canceled",
        ),
    ],
)
async def test_refund_dispute_and_cancellation_never_leave_pilot_paid(
    monkeypatch,
    tmp_path,
    event_type,
    amount,
    provider_status,
    expected_status,
):
    provider_object = _reversal_object(
        event_type,
        amount=amount,
        status=provider_status,
    )
    verifier = _install_reversal_verification(monkeypatch, provider_object)
    async with _isolated_database(tmp_path, f"reversal_{event_type}_{expected_status}") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status="paid")
            payment = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
            )
            db.add(payment)
            await db.commit()

            first = await handle_stripe_webhook(
                f"evt_{event_type}_{expected_status}",
                event_type,
                provider_object,
                db,
            )
            duplicate = await handle_stripe_webhook(
                f"evt_{event_type}_{expected_status}",
                event_type,
                provider_object,
                db,
            )
            persisted_payment = (
                await db.execute(select(PilotPayment))
            ).scalar_one()
            persisted_request = (
                await db.execute(select(PilotRequest))
            ).scalar_one()

            assert first["status"] == expected_status
            assert duplicate["status"] == "duplicate"
            assert persisted_payment.status == expected_status
            assert persisted_request.status == expected_status
            assert persisted_payment.status != "paid"
            verifier.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status", ["failed", "canceled"])
async def test_terminal_refund_update_is_consumed_once_without_reactivation(
    monkeypatch,
    tmp_path,
    provider_status,
):
    provider_object = _reversal_object(
        "refund.updated",
        status=provider_status,
    )
    verifier = _install_reversal_verification(monkeypatch, provider_object)
    event_id = f"evt_refund_{provider_status}"
    async with _isolated_database(tmp_path, event_id) as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status="paid")
            payment = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
            )
            db.add(payment)
            await db.commit()

            first = await handle_stripe_webhook(
                event_id,
                "refund.updated",
                provider_object,
                db,
            )
            duplicate = await handle_stripe_webhook(
                event_id,
                "refund.updated",
                provider_object,
                db,
            )
            await db.refresh(payment)
            await db.refresh(pilot_request)
            event = await db.scalar(
                select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
            )

            assert first["status"] == "paid"
            assert duplicate["status"] == "duplicate"
            assert payment.status == "paid"
            assert pilot_request.status == "paid"
            assert payment.payment_status == f"refund_{provider_status}"
            assert payment.stripe_event_id == event_id
            assert event is not None and event.status == "processed"
            assert event.attempt_count == 1
            verifier.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status", ["failed", "canceled"])
@pytest.mark.parametrize(
    ("adverse_status", "prior_payment_status", "prior_event_id"),
    [
        ("manual_review", "partially_refunded", "evt_prior_partial_refund"),
        ("failed", "refunded", "evt_prior_full_refund"),
    ],
)
async def test_terminal_refund_update_preserves_prior_adverse_state(
    monkeypatch,
    tmp_path,
    provider_status,
    adverse_status,
    prior_payment_status,
    prior_event_id,
):
    provider_object = _reversal_object(
        "refund.updated",
        status=provider_status,
    )
    verifier = _install_reversal_verification(monkeypatch, provider_object)
    event_id = f"evt_{adverse_status}_refund_{provider_status}"
    async with _isolated_database(tmp_path, event_id) as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status=adverse_status)
            payment = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
                status=adverse_status,
                payment_status=prior_payment_status,
            )
            payment.stripe_event_id = prior_event_id
            db.add(payment)
            await db.commit()

            first = await handle_stripe_webhook(
                event_id,
                "refund.updated",
                provider_object,
                db,
            )
            duplicate = await handle_stripe_webhook(
                event_id,
                "refund.updated",
                provider_object,
                db,
            )
            await db.refresh(payment)
            await db.refresh(pilot_request)
            event = await db.scalar(
                select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
            )

            assert first["status"] == adverse_status
            assert duplicate["status"] == "duplicate"
            assert payment.status == adverse_status
            assert pilot_request.status == adverse_status
            assert payment.payment_status == prior_payment_status
            assert payment.stripe_event_id == prior_event_id
            assert event is not None and event.status == "processed"
            assert event.attempt_count == 1
            verifier.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminal_refund_update_retries_after_atomic_finalization_failure(
    monkeypatch,
    tmp_path,
):
    provider_object = _reversal_object("refund.updated", status="failed")
    _install_reversal_verification(monkeypatch, provider_object)
    real_update = webhook_handler_service.update_webhook_status
    update_attempts = 0

    async def fail_first_final_status(*args, **kwargs):
        nonlocal update_attempts
        update_attempts += 1
        if update_attempts == 1:
            raise OperationalError(
                "UPDATE webhook_events",
                {},
                RuntimeError("final status unavailable"),
            )
        return await real_update(*args, **kwargs)

    monkeypatch.setattr(
        webhook_handler_service,
        "update_webhook_status",
        fail_first_final_status,
    )
    event_id = "evt_terminal_refund_retry"
    async with _isolated_database(tmp_path, event_id) as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status="paid")
            payment = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
            )
            db.add(payment)
            await db.commit()

            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    event_id,
                    "refund.updated",
                    provider_object,
                    db,
                )

            await db.refresh(payment)
            await db.refresh(pilot_request)
            event = await db.scalar(
                select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
            )
            assert payment.status == "paid"
            assert pilot_request.status == "paid"
            assert payment.payment_status == "paid"
            assert payment.stripe_event_id == "evt_original"
            assert event is not None and event.status == "retryable_failure"

            replay = await handle_stripe_webhook(
                event_id,
                "refund.updated",
                provider_object,
                db,
            )
            duplicate = await handle_stripe_webhook(
                event_id,
                "refund.updated",
                provider_object,
                db,
            )
            await db.refresh(payment)
            await db.refresh(pilot_request)
            await db.refresh(event)

            assert replay["status"] == "paid"
            assert duplicate["status"] == "duplicate"
            assert payment.status == "paid"
            assert pilot_request.status == "paid"
            assert payment.payment_status == "refund_failed"
            assert payment.stripe_event_id == event_id
            assert event.status == "processed"
            assert event.attempt_count == 2


@pytest.mark.asyncio
async def test_unrelated_reversal_is_classified_once_without_retry_loop(
    monkeypatch,
    tmp_path,
):
    provider_object = _reversal_object("charge.refunded")
    verifier = _install_reversal_verification(monkeypatch, provider_object)
    session_lookup = AsyncMock(
        return_value={
            "data": [
                _reversal_session(payment_link_id="plink_foreign"),
            ]
        }
    )
    monkeypatch.setattr(
        pilot_payment_service,
        "retrieve_pilot_reversal_sessions",
        session_lookup,
    )
    async with _isolated_database(tmp_path, "unrelated_reversal") as sessions:
        async with sessions() as db:
            result = await handle_stripe_webhook(
                "evt_unrelated_refund",
                "charge.refunded",
                _reversal_object("charge.refunded"),
                db,
            )

            assert result["status"] == "ignored"
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 0
            event = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_unrelated_refund"
                )
            )
            assert event is not None and event.status == "ignored"
            verifier.assert_awaited_once()
            session_lookup.assert_awaited_once_with("pi_reversal")


@pytest.mark.asyncio
async def test_unconfigured_pilot_reversal_is_ignored_without_retry_loop(
    monkeypatch,
    tmp_path,
):
    for field_name in billing_service._PILOT_OPTIONAL_FIELDS:
        monkeypatch.setattr(settings, field_name, "")
    monkeypatch.setattr(settings, "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON", "[]")
    verifier = AsyncMock(side_effect=AssertionError("Disabled Pilot reached Stripe"))
    monkeypatch.setattr(
        pilot_payment_service,
        "verify_pilot_reversal_event",
        verifier,
    )

    async with _isolated_database(tmp_path, "disabled_pilot_reversal") as sessions:
        async with sessions() as db:
            first = await handle_stripe_webhook(
                "evt_disabled_pilot_refund",
                "charge.refunded",
                _reversal_object("charge.refunded"),
                db,
            )
            duplicate = await handle_stripe_webhook(
                "evt_disabled_pilot_refund",
                "charge.refunded",
                _reversal_object("charge.refunded"),
                db,
            )
            event = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_disabled_pilot_refund"
                )
            )

            assert first["status"] == "ignored"
            assert duplicate["status"] == "duplicate"
            assert event is not None and event.status == "ignored"
            assert event.attempt_count == 1
            verifier.assert_not_awaited()


@pytest.mark.asyncio
async def test_partially_configured_pilot_reversal_remains_retryable_fail_closed(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRICE_ID", "")
    verifier = AsyncMock(side_effect=AssertionError("Partial config reached Stripe"))
    monkeypatch.setattr(
        pilot_payment_service,
        "verify_pilot_reversal_event",
        verifier,
    )

    async with _isolated_database(tmp_path, "partial_pilot_reversal") as sessions:
        async with sessions() as db:
            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    "evt_partial_pilot_refund",
                    "charge.refunded",
                    _reversal_object("charge.refunded"),
                    db,
                )
            event = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_partial_pilot_refund"
                )
            )

            assert event is not None and event.status == "retryable_failure"
            assert event.attempt_count == 1
            verifier.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "expected_status"),
    [
        pytest.param("charge.refunded", "failed", id="refund-after-link-rotation"),
        pytest.param(
            "charge.dispute.created",
            "manual_review",
            id="dispute-after-link-rotation",
        ),
    ],
)
async def test_reversal_after_payment_link_rotation_uses_stored_contract(
    monkeypatch,
    tmp_path,
    event_type,
    expected_status,
):
    monkeypatch.setattr(settings, "STRIPE_PILOT_PAYMENT_LINK_ID", "plink_rotated")
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PAYMENT_LINK_URL",
        "https://buy.stripe.com/rotatedPilot",
    )
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON",
        _previous_pilot_contract_json(
            product_id=PRODUCT_ID,
            price_id=PRICE_ID,
            payment_link_id=PAYMENT_LINK_ID,
            payment_link_url=PAYMENT_LINK_URL,
        ),
    )
    provider_object = _reversal_object(event_type)
    _install_reversal_verification(monkeypatch, provider_object)

    async with _isolated_database(tmp_path, f"rotation_{event_type}") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status="paid")
            payment = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
            )
            db.add(payment)
            await db.commit()

            first = await handle_stripe_webhook(
                f"evt_rotation_{event_type}",
                event_type,
                provider_object,
                db,
            )
            duplicate = await handle_stripe_webhook(
                f"evt_rotation_{event_type}",
                event_type,
                provider_object,
                db,
            )
            await db.refresh(payment)
            await db.refresh(pilot_request)

            assert first["status"] == expected_status
            assert duplicate["status"] == "duplicate"
            assert payment.status == expected_status
            assert pilot_request.status == expected_status
            assert payment.stripe_payment_link_id == PAYMENT_LINK_ID
            assert payment.stripe_price_id == PRICE_ID


@pytest.mark.asyncio
async def test_link_rotation_rejects_session_that_does_not_match_stored_payment(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(settings, "STRIPE_PILOT_PAYMENT_LINK_ID", "plink_rotated")
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PAYMENT_LINK_URL",
        "https://buy.stripe.com/rotatedPilot",
    )
    provider_object = _reversal_object("charge.refunded")
    _install_reversal_verification(monkeypatch, provider_object)
    monkeypatch.setattr(
        pilot_payment_service,
        "retrieve_pilot_reversal_sessions",
        AsyncMock(
            return_value={
                "data": [_reversal_session(payment_link_id="plink_foreign")]
            }
        ),
    )

    async with _isolated_database(tmp_path, "rotation_foreign_session") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status="paid")
            payment = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
            )
            db.add(payment)
            await db.commit()

            result = await handle_stripe_webhook(
                "evt_rotation_foreign",
                "charge.refunded",
                provider_object,
                db,
            )
            await db.refresh(payment)
            await db.refresh(pilot_request)

            assert result["status"] == "rejected"
            assert payment.status == "paid"
            assert pilot_request.status == "paid"


@pytest.mark.asyncio
async def test_adverse_event_before_checkout_commit_returns_503_then_replays_once(
    monkeypatch,
    tmp_path,
):
    provider_object = _reversal_object("charge.refunded")
    verifier = _install_reversal_verification(monkeypatch, provider_object)
    event = {
        "id": "evt_refund_race",
        "type": "charge.refunded",
        "data": {"object": provider_object},
    }
    monkeypatch.setattr(
        billing_router.stripe.Webhook,
        "construct_event",
        lambda **_kwargs: event,
    )

    async with _isolated_database(tmp_path, "refund_before_checkout_commit") as sessions:
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
                        WebhookEvent.stripe_event_id == "evt_refund_race"
                    )
                )
            ).scalar_one()
            assert retryable.status == "retryable_failure"
            assert retryable.attempt_count == 1
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 0

            pilot_request = await _add_request(db, status="paid")
            pilot_request_id = pilot_request.id
            db.add(
                _existing_payment(
                    request=pilot_request,
                    session_id="cs_reversal",
                    payment_intent_id="pi_reversal",
                )
            )
            await db.commit()

            replay = await billing_router.stripe_webhook(
                _request(),
                db,
                stripe_signature="valid-local-signature",
            )
            duplicate = await billing_router.stripe_webhook(
                _request(),
                db,
                stripe_signature="valid-local-signature",
            )
            payment = (await db.execute(select(PilotPayment))).scalar_one()
            persisted_request = (
                await db.execute(select(PilotRequest))
            ).scalar_one()
            await db.refresh(retryable)

            assert replay == {
                "received": True,
                "status": "failed",
                "type": "charge.refunded",
            }
            assert duplicate["status"] == "duplicate"
            assert retryable.status == "processed"
            assert retryable.attempt_count == 2
            assert payment.status == "failed"
            assert persisted_request.status == "failed"
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 1
            assert verifier.await_count == 2
            assert pilot_payment_service.retrieve_pilot_reversal_sessions.await_count == 2

            _install_line_items(monkeypatch)
            late_success = await handle_stripe_webhook(
                "evt_late_success_after_race",
                "checkout.session.async_payment_succeeded",
                _valid_session(
                    session_id="cs_reversal",
                    payment_intent_id="pi_reversal",
                    request_id=pilot_request_id,
                ),
                db,
            )
            assert late_success["status"] == "failed"
            assert payment.status == "failed"
            assert persisted_request.status == "failed"


@pytest.mark.asyncio
async def test_adverse_state_rolls_back_before_retry_marker_and_503(
    monkeypatch,
    tmp_path,
):
    provider_object = _reversal_object("charge.refunded")
    _install_reversal_verification(monkeypatch, provider_object)
    real_update = webhook_handler_service.update_webhook_status
    update_attempts = 0

    async def fail_first_final_status(*args, **kwargs):
        nonlocal update_attempts
        update_attempts += 1
        if update_attempts == 1:
            raise OperationalError(
                "UPDATE webhook_events",
                {},
                RuntimeError("final status unavailable"),
            )
        return await real_update(*args, **kwargs)

    monkeypatch.setattr(
        webhook_handler_service,
        "update_webhook_status",
        fail_first_final_status,
    )
    async with _isolated_database(tmp_path, "adverse_atomic_rollback") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status="paid")
            payment = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
            )
            db.add(payment)
            await db.commit()

            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    "evt_adverse_rollback",
                    "charge.refunded",
                    provider_object,
                    db,
                )

            await db.refresh(payment)
            await db.refresh(pilot_request)
            retryable = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_adverse_rollback"
                )
            )
            assert payment.status == "paid"
            assert pilot_request.status == "paid"
            assert retryable is not None
            assert retryable.status == "retryable_failure"

            replay = await handle_stripe_webhook(
                "evt_adverse_rollback",
                "charge.refunded",
                provider_object,
                db,
            )
            duplicate = await handle_stripe_webhook(
                "evt_adverse_rollback",
                "charge.refunded",
                provider_object,
                db,
            )
            await db.refresh(payment)
            await db.refresh(pilot_request)
            await db.refresh(retryable)

            assert replay["status"] == "failed"
            assert duplicate["status"] == "duplicate"
            assert payment.status == "failed"
            assert pilot_request.status == "failed"
            assert retryable.status == "processed"
            assert retryable.attempt_count == 2


@pytest.mark.asyncio
async def test_permanent_pilot_identity_mismatch_is_rejected_without_retry(
    monkeypatch,
    tmp_path,
):
    provider_object = _reversal_object("charge.refunded")
    _install_reversal_verification(monkeypatch, provider_object)
    pilot_payment_service.retrieve_pilot_reversal_sessions.return_value = {
        "data": [_reversal_session(amount_total=29_699)]
    }
    async with _isolated_database(tmp_path, "adverse_permanent_rejection") as sessions:
        async with sessions() as db:
            first = await handle_stripe_webhook(
                "evt_adverse_rejected",
                "charge.refunded",
                provider_object,
                db,
            )
            duplicate = await handle_stripe_webhook(
                "evt_adverse_rejected",
                "charge.refunded",
                provider_object,
                db,
            )
            event = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_adverse_rejected"
                )
            )

            assert first["status"] == "rejected"
            assert duplicate["status"] == "duplicate"
            assert event is not None and event.status == "rejected"
            assert event.attempt_count == 1
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 0


@pytest.mark.asyncio
async def test_provider_identity_checks_finish_before_postgres_row_lock(monkeypatch):
    provider_object = _reversal_object("charge.refunded")
    order: list[str] = []

    async def verify(*_args):
        order.append("verify")
        return (
            provider_object,
            pilot_stripe_contract_service.load_pilot_stripe_config(),
        )

    async def retrieve_sessions(payment_intent_id):
        assert payment_intent_id == "pi_reversal"
        order.append("sessions")
        return {"data": [_reversal_session()]}

    async def execute(_statement):
        order.append("db")
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        return result

    monkeypatch.setattr(
        pilot_payment_service,
        "verify_pilot_reversal_event",
        verify,
    )
    monkeypatch.setattr(
        pilot_payment_service,
        "retrieve_pilot_reversal_sessions",
        retrieve_sessions,
    )
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute)

    with pytest.raises(pilot_payment_service.PilotAdverseEventPendingCommit):
        await pilot_payment_service.process_pilot_reversal_event(
            "evt_order",
            "charge.refunded",
            provider_object,
            db,
        )

    assert order == ["verify", "sessions", "db"]
    sql = str(
        pilot_payment_service._pilot_payment_for_update_statement(
            "pi_reversal"
        ).compile(dialect=postgresql.dialect())
    )
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
async def test_provider_preparation_has_no_open_transaction_before_claim(
    monkeypatch,
    tmp_path,
):
    provider_object = _reversal_object("charge.refunded")
    _install_reversal_verification(monkeypatch, provider_object)
    pilot_payment_service.retrieve_pilot_reversal_sessions.return_value = {
        "data": [_reversal_session(payment_link_id="plink_foreign")]
    }
    real_prepare = webhook_handler_service.prepare_stripe_event
    real_claim = webhook_handler_service.claim_webhook_event
    order: list[str] = []

    async with _isolated_database(tmp_path, "provider_before_claim") as sessions:
        async with sessions() as db:

            async def prepare(*args, **kwargs):
                assert db.in_transaction() is False
                order.append("provider")
                prepared = await real_prepare(*args, **kwargs)
                assert db.in_transaction() is False
                return prepared

            async def claim(*args, **kwargs):
                assert db.in_transaction() is False
                order.append("claim")
                return await real_claim(*args, **kwargs)

            monkeypatch.setattr(
                webhook_handler_service,
                "prepare_stripe_event",
                prepare,
            )
            monkeypatch.setattr(
                webhook_handler_service,
                "claim_webhook_event",
                claim,
            )

            result = await handle_stripe_webhook(
                "evt_provider_before_claim",
                "charge.refunded",
                provider_object,
                db,
            )

            assert result["status"] == "ignored"
            assert order == ["provider", "claim"]


@pytest.mark.asyncio
async def test_provider_preparation_failure_is_persisted_as_retryable(
    monkeypatch,
    tmp_path,
):
    async with _isolated_database(tmp_path, "provider_retryable_failure") as sessions:
        async with sessions() as db:

            async def unavailable(*_args, **_kwargs):
                assert db.in_transaction() is False
                raise pilot_stripe_contract_service.PilotStripeProviderUnavailable(
                    "synthetic provider outage"
                )

            monkeypatch.setattr(
                webhook_handler_service,
                "prepare_stripe_event",
                unavailable,
            )

            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    "evt_provider_retryable",
                    "charge.refunded",
                    _reversal_object("charge.refunded"),
                    db,
                )

            event = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_provider_retryable"
                )
            )
            assert event is not None
            assert event.status == "retryable_failure"
            assert event.attempt_count == 1
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 0


@pytest.mark.asyncio
async def test_distinct_adverse_events_are_monotone_out_of_order(
    monkeypatch,
    tmp_path,
):
    async with _isolated_database(tmp_path, "adverse_out_of_order") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status="paid")
            payment = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
            )
            db.add(payment)
            await db.commit()

            full_refund = _reversal_object("charge.refunded")
            _install_reversal_verification(monkeypatch, full_refund)
            first = await handle_stripe_webhook(
                "evt_full_refund_first",
                "charge.refunded",
                full_refund,
                db,
            )

            partial_refund = _reversal_object("charge.refunded", amount=10_000)
            _install_reversal_verification(monkeypatch, partial_refund)
            second = await handle_stripe_webhook(
                "evt_partial_refund_late",
                "charge.refunded",
                partial_refund,
                db,
            )

            won_dispute = _reversal_object(
                "charge.dispute.closed",
                status="won",
            )
            _install_reversal_verification(monkeypatch, won_dispute)
            third = await handle_stripe_webhook(
                "evt_won_dispute_late",
                "charge.dispute.closed",
                won_dispute,
                db,
            )
            duplicate = await handle_stripe_webhook(
                "evt_won_dispute_late",
                "charge.dispute.closed",
                won_dispute,
                db,
            )
            persisted_payment = (
                await db.execute(select(PilotPayment))
            ).scalar_one()
            persisted_request = (
                await db.execute(select(PilotRequest))
            ).scalar_one()
            events = list((await db.execute(select(WebhookEvent))).scalars())

            assert first["status"] == "failed"
            assert second["status"] == "failed"
            assert third["status"] == "failed"
            assert duplicate["status"] == "duplicate"
            assert persisted_payment.status == "failed"
            assert persisted_payment.payment_status == "refunded"
            assert persisted_request.status == "failed"
            assert len(events) == 3
            assert all(event.status == "processed" for event in events)


@pytest.mark.asyncio
async def test_refunded_payment_cannot_be_reactivated_by_late_success(
    monkeypatch,
    tmp_path,
):
    provider_object = _reversal_object("charge.refunded")
    _install_reversal_verification(monkeypatch, provider_object)
    async with _isolated_database(tmp_path, "refund_no_reactivation") as sessions:
        async with sessions() as db:
            pilot_request = await _add_request(db, status="paid")
            payment = _existing_payment(
                request=pilot_request,
                session_id="cs_reversal",
                payment_intent_id="pi_reversal",
            )
            db.add(payment)
            await db.commit()

            refunded = await handle_stripe_webhook(
                "evt_refund_before_late_success",
                "charge.refunded",
                provider_object,
                db,
            )
            _install_line_items(monkeypatch)
            late_success = await handle_stripe_webhook(
                "evt_late_success_after_refund",
                "checkout.session.async_payment_succeeded",
                _valid_session(
                    session_id="cs_reversal",
                    payment_intent_id="pi_reversal",
                    request_id=pilot_request.id,
                ),
                db,
            )

            assert refunded["status"] == "failed"
            assert late_success["status"] == "failed"
            assert payment.status == "failed"
            assert pilot_request.status == "failed"
            assert payment.status != "paid"


@pytest.mark.asyncio
async def test_legacy_checkout_and_final_status_commit_atomically(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        credit_service,
        "_sync_workspace_credit_projection",
        AsyncMock(),
    )
    async with _isolated_legacy_database(tmp_path, "legacy_atomic_success") as sessions:
        async with sessions() as db:
            user = User(
                email="legacy-success@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Legacy Success",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            user_id = user.id
            payload = _legacy_credit_checkout(user_id, session_id="cs_legacy_success")

            first = await handle_stripe_webhook(
                "evt_legacy_success",
                "checkout.session.completed",
                payload,
                db,
            )
            duplicate = await handle_stripe_webhook(
                "evt_legacy_success",
                "checkout.session.completed",
                payload,
                db,
            )

            persisted_user = await db.scalar(select(User).where(User.id == user_id))
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            event = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_legacy_success"
                )
            )
            assert first["status"] == "processed"
            assert duplicate["status"] == "duplicate"
            assert persisted_user is not None and persisted_user.credits == 25
            assert ledger_count == 1
            assert event is not None and event.status == "processed"


@pytest.mark.asyncio
async def test_pre_rotation_credit_checkout_paid_after_rotation_is_fulfilled_once(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        credit_service,
        "_sync_workspace_credit_projection",
        AsyncMock(),
    )
    event_id = "evt_credit_created_before_rotation"
    async with _isolated_legacy_database(tmp_path, "credit_before_rotation") as sessions:
        async with sessions() as db:
            user = User(
                email="credit-before-rotation@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Credit Before Rotation",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            payload = _legacy_credit_checkout(
                user.id,
                session_id="cs_credit_before_rotation",
                created=CREDIT_OLD_PRICE_CREATED + 100,
            )
            boundaries = _install_credit_provider_contract(
                monkeypatch,
                payload,
                event_id=event_id,
                line_items=_credit_line_items(
                    price_id=CREDIT_OLD_PRICE_ID,
                    price_created=CREDIT_OLD_PRICE_CREATED,
                    price_active=False,
                ),
            )

            first = await handle_stripe_webhook(
                event_id,
                "checkout.session.completed",
                payload,
                db,
            )
            duplicate = await handle_stripe_webhook(
                event_id,
                "checkout.session.completed",
                payload,
                db,
            )
            second_event = await handle_stripe_webhook(
                "evt_credit_before_rotation_distinct",
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            events = list((await db.execute(select(WebhookEvent))).scalars())

            assert first["status"] == "processed"
            assert duplicate["status"] == "duplicate"
            assert second_event["status"] == "processed"
            assert user.credits == CREDIT_PACK_SIZE
            assert ledger_count == 1
            assert len(events) == 2
            assert all(event.status == "processed" for event in events)
            assert boundaries["event"].await_count == 2
            assert boundaries["session"].await_count == 2


@pytest.mark.asyncio
async def test_admin_credit_reprocess_prepares_before_mutation_and_retries_once(
    tmp_path,
    monkeypatch,
):
    operation_order = []

    async def prepare_event(*args, **kwargs):
        operation_order.append("prepare")
        return await billing_service.prepare_stripe_event(*args, **kwargs)

    async def update_status(event_id, status, error, db):
        operation_order.append(status)
        return await billing_service.update_webhook_status(
            event_id,
            status,
            error,
            db,
        )

    monkeypatch.setattr(
        credit_service,
        "_sync_workspace_credit_projection",
        AsyncMock(),
    )
    monkeypatch.setattr(admin_router, "prepare_stripe_event", prepare_event)
    monkeypatch.setattr(admin_router, "update_webhook_status", update_status)
    async with _isolated_legacy_database(tmp_path, "admin_credit_reprocess") as sessions:
        user_id = uuid.uuid4()
        event_id = "evt_admin_credit_reprocess"
        payload = _legacy_credit_checkout(
            user_id,
            session_id="cs_admin_credit_reprocess",
        )
        monkeypatch.setattr(
            admin_router.stripe.Event,
            "retrieve",
            lambda requested_id: _credit_event(requested_id, payload),
        )

        async with sessions() as db:
            db.add(
                User(
                    id=user_id,
                    email="admin-credit-reprocess@example.com",
                    password_hash="unused",
                    full_name="Admin Credit Reprocess",
                    stripe_customer_id="cus_legacy",
                    credits=0,
                )
            )
            db.add(
                WebhookEvent(
                    stripe_event_id=event_id,
                    event_type="checkout.session.completed",
                    status="retryable_failure",
                    attempt_count=1,
                    error="prior provider outage",
                )
            )
            await db.commit()

            first = await admin_router.admin_reprocess_webhook(
                event_id,
                SimpleNamespace(id=uuid.uuid4()),
                db,
            )
            second = await admin_router.admin_reprocess_webhook(
                event_id,
                SimpleNamespace(id=uuid.uuid4()),
                db,
                SimpleNamespace(force=True),
            )

            user = await db.get(User, user_id)
            assert user is not None
            await db.refresh(user)
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            stored_event = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == event_id
                )
            )

            assert first["status"] == "processed"
            assert first["forced"] is False
            assert second["status"] == "processed"
            assert second["forced"] is True
            assert user.credits == CREDIT_PACK_SIZE
            assert ledger_count == 1
            assert stored_event is not None
            assert stored_event.status == "processed"
            assert stored_event.error is None
            assert operation_order == [
                "prepare",
                "processing",
                "processed",
                "prepare",
                "processing",
                "processed",
            ]


@pytest.mark.asyncio
async def test_old_credit_price_cannot_fulfill_session_created_after_rotation(
    monkeypatch,
    tmp_path,
):
    event_id = "evt_old_price_new_session"
    async with _isolated_legacy_database(tmp_path, "old_price_new_session") as sessions:
        async with sessions() as db:
            user = User(
                email="old-price-new-session@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Old Price New Session",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            payload = _legacy_credit_checkout(
                user.id,
                session_id="cs_old_price_created_too_late",
                created=CREDIT_CURRENT_PRICE_CREATED + 1,
            )
            _install_credit_provider_contract(
                monkeypatch,
                payload,
                event_id=event_id,
                line_items=_credit_line_items(
                    price_id=CREDIT_OLD_PRICE_ID,
                    price_created=CREDIT_OLD_PRICE_CREATED,
                    price_active=False,
                ),
            )

            result = await handle_stripe_webhook(
                event_id,
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            event = await db.scalar(
                select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
            )
            assert result["status"] == "rejected"
            assert user.credits == 0
            assert ledger_count == 0
            assert event is not None and event.status == "rejected"


@pytest.mark.asyncio
async def test_pre_rotation_timestamp_cannot_authorize_unrelated_old_price(
    monkeypatch,
    tmp_path,
):
    event_id = "evt_unrelated_old_credit_price"
    async with _isolated_legacy_database(tmp_path, "unrelated_old_price") as sessions:
        async with sessions() as db:
            user = User(
                email="unrelated-old-price@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Unrelated Old Price",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            payload = _legacy_credit_checkout(
                user.id,
                session_id="cs_unrelated_old_price",
                created=CREDIT_OLD_PRICE_CREATED + 100,
            )
            _install_credit_provider_contract(
                monkeypatch,
                payload,
                event_id=event_id,
                line_items=_credit_line_items(
                    price_id="price_unrelated_old",
                    price_created=CREDIT_OLD_PRICE_CREATED,
                    price_active=False,
                    product_id="prod_unrelated",
                ),
            )

            result = await handle_stripe_webhook(
                event_id,
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            assert result["status"] == "rejected"
            assert user.credits == 0
            assert ledger_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_contract",
    [
        "event_account",
        "account_resource",
        "foreign_session",
        "mode",
        "expired",
        "livemode",
        "currency",
        "amount",
        "owner",
        "foreign_customer",
        "unpaid",
    ],
)
async def test_credit_provider_or_owner_mismatch_never_grants_value(
    monkeypatch,
    tmp_path,
    invalid_contract,
):
    event_id = f"evt_credit_mismatch_{invalid_contract}"
    async with _isolated_legacy_database(
        tmp_path,
        f"credit_mismatch_{invalid_contract}",
    ) as sessions:
        async with sessions() as db:
            user = User(
                email=f"credit-{invalid_contract}@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Credit Contract Mismatch",
                credits=0,
                stripe_customer_id=(
                    "cus_other" if invalid_contract == "foreign_customer" else "cus_legacy"
                ),
            )
            db.add(user)
            await db.commit()
            payload = _legacy_credit_checkout(
                user.id,
                session_id=f"cs_credit_mismatch_{invalid_contract}",
                payment_status="unpaid" if invalid_contract == "unpaid" else "paid",
            )
            if invalid_contract == "mode":
                payload["mode"] = "subscription"
            elif invalid_contract == "expired":
                payload["status"] = "expired"
            provider_event = _credit_event(event_id, payload)
            provider_session = _credit_provider_session(payload)
            account = _credit_account()
            line_items = _credit_line_items()
            customer = _credit_customer(payload)
            if invalid_contract == "event_account":
                provider_event["account"] = "acct_foreign"
            elif invalid_contract == "account_resource":
                account = _credit_account(account_id="acct_foreign")
            elif invalid_contract == "foreign_session":
                provider_event["data"]["object"]["id"] = "cs_foreign"
            elif invalid_contract == "livemode":
                provider_session["livemode"] = True
            elif invalid_contract == "currency":
                line_items = _credit_line_items(currency="cad")
            elif invalid_contract == "amount":
                provider_session["payment_intent"]["amount_received"] -= 1
            elif invalid_contract == "owner":
                customer = _credit_customer(payload, user_id=uuid.uuid4())
            _install_credit_provider_contract(
                monkeypatch,
                payload,
                event_id=event_id,
                provider_event=provider_event,
                provider_session=provider_session,
                account=account,
                customer=customer,
                line_items=line_items,
            )

            result = await handle_stripe_webhook(
                event_id,
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            assert result["status"] == "rejected"
            assert user.credits == 0
            assert ledger_count == 0


@pytest.mark.asyncio
async def test_credit_provider_failure_rolls_back_and_replay_is_atomic(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        credit_service,
        "_sync_workspace_credit_projection",
        AsyncMock(),
    )
    event_id = "evt_credit_provider_retry"
    async with _isolated_legacy_database(tmp_path, "credit_provider_retry") as sessions:
        async with sessions() as db:
            user = User(
                email="credit-provider-retry@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Credit Provider Retry",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            payload = _legacy_credit_checkout(
                user.id,
                session_id="cs_credit_provider_retry",
            )
            boundaries = _install_credit_provider_contract(
                monkeypatch,
                payload,
                event_id=event_id,
            )
            boundaries["session"].side_effect = [
                stripe.error.APIConnectionError("local provider outage"),
                _credit_provider_session(payload),
            ]

            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    event_id,
                    "checkout.session.completed",
                    payload,
                    db,
                )

            await db.refresh(user)
            event = await db.scalar(
                select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
            )
            ledger_after_failure = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            assert user.credits == 0
            assert ledger_after_failure == 0
            assert event is not None and event.status == "retryable_failure"

            retry = await handle_stripe_webhook(
                event_id,
                "checkout.session.completed",
                payload,
                db,
            )
            duplicate = await handle_stripe_webhook(
                event_id,
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            await db.refresh(event)
            ledger_after_retry = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            assert retry["status"] == "processed"
            assert duplicate["status"] == "duplicate"
            assert user.credits == CREDIT_PACK_SIZE
            assert ledger_after_retry == 1
            assert event.status == "processed"
            assert event.attempt_count == 2


@pytest.mark.asyncio
async def test_new_credit_checkout_creation_uses_only_current_price(monkeypatch):
    from api.schemas.billing import CreditPurchaseRequest

    user = MagicMock()
    user.id = uuid.uuid4()
    customer = AsyncMock(return_value="cus_current_credit_price")
    checkout_create = MagicMock(
        return_value=MagicMock(url="https://checkout.stripe.test/current")
    )
    retrieve_price = AsyncMock(return_value=_credit_price())
    monkeypatch.setattr(billing_service, "retrieve_credit_price", retrieve_price)
    monkeypatch.setattr(billing_router, "get_or_create_stripe_customer", customer)
    monkeypatch.setattr(
        billing_router.stripe.checkout.Session,
        "create",
        checkout_create,
    )

    response = await billing_router.purchase_credits(
        CreditPurchaseRequest(quantity=2),
        user,
        AsyncMock(),
    )

    assert response.credits_to_add == 2 * CREDIT_PACK_SIZE
    retrieve_price.assert_awaited_once_with(CREDIT_PRICE_ID)
    assert checkout_create.call_args.kwargs["line_items"] == [
        {"price": CREDIT_PRICE_ID, "quantity": 2}
    ]
    assert "payment_method_types" not in checkout_create.call_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_contract",
    [
        "price_metadata_missing",
        "product_metadata_missing",
        "product_metadata_contradictory",
        "credits_zero",
        "credits_negative",
        "credits_non_numeric",
        "price_inactive",
        "product_inactive",
        "product_unexpanded",
        "amount",
        "currency",
        "recurring",
        "provider_outage",
        "provider_timeout",
    ],
)
async def test_invalid_credit_catalog_never_creates_customer_or_checkout(
    monkeypatch,
    invalid_contract,
):
    from api.schemas.billing import CreditPurchaseRequest

    price = _credit_price()
    if invalid_contract == "price_metadata_missing":
        price["metadata"] = {}
    elif invalid_contract == "product_metadata_missing":
        price["product"]["metadata"] = {}
    elif invalid_contract == "product_metadata_contradictory":
        price["product"]["metadata"]["credits"] = str(CREDIT_PACK_SIZE + 1)
    elif invalid_contract == "credits_zero":
        price["metadata"]["credits"] = "0"
    elif invalid_contract == "credits_negative":
        price["metadata"]["credits"] = "-1"
    elif invalid_contract == "credits_non_numeric":
        price["metadata"]["credits"] = "twenty-five"
    elif invalid_contract == "price_inactive":
        price["active"] = False
    elif invalid_contract == "product_inactive":
        price["product"]["active"] = False
    elif invalid_contract == "product_unexpanded":
        price["product"] = CREDIT_PRODUCT_ID
    elif invalid_contract == "amount":
        price["unit_amount"] = CREDIT_UNIT_AMOUNT + 1
    elif invalid_contract == "currency":
        price["currency"] = "cad"
    elif invalid_contract == "recurring":
        price["type"] = "recurring"
        price["recurring"] = {"interval": "month"}

    provider_error = {
        "provider_outage": stripe.error.APIConnectionError("local outage"),
        "provider_timeout": TimeoutError("local timeout"),
    }.get(invalid_contract)
    retrieve_price = AsyncMock(
        side_effect=provider_error,
        return_value=None if provider_error else price,
    )
    customer = AsyncMock()
    checkout_create = MagicMock()
    monkeypatch.setattr(billing_service, "retrieve_credit_price", retrieve_price)
    monkeypatch.setattr(billing_router, "get_or_create_stripe_customer", customer)
    monkeypatch.setattr(
        billing_router.stripe.checkout.Session,
        "create",
        checkout_create,
    )

    with pytest.raises(HTTPException) as exc_info:
        await billing_router.purchase_credits(
            CreditPurchaseRequest(quantity=1),
            MagicMock(id=uuid.uuid4()),
            AsyncMock(),
        )

    assert exc_info.value.status_code == 503
    retrieve_price.assert_awaited_once_with(CREDIT_PRICE_ID)
    customer.assert_not_awaited()
    checkout_create.assert_not_called()


@pytest.mark.asyncio
async def test_partial_credit_configuration_stays_retryable_without_value(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(settings, "STRIPE_CREDIT_PRICE_ID", "")
    monkeypatch.setattr(
        billing_service,
        "verify_credit_checkout_session",
        _REAL_VERIFY_CREDIT_CHECKOUT,
    )
    event_id = "evt_partial_credit_configuration"
    async with _isolated_legacy_database(tmp_path, "partial_credit_config") as sessions:
        async with sessions() as db:
            user = User(
                email="partial-credit-config@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Partial Credit Config",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            payload = _legacy_credit_checkout(
                user.id,
                session_id="cs_partial_credit_configuration",
            )

            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    event_id,
                    "checkout.session.completed",
                    payload,
                    db,
                )

            await db.refresh(user)
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            event = await db.scalar(
                select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
            )
            assert user.credits == 0
            assert ledger_count == 0
            assert event is not None
            assert event.status == "retryable_failure"
            assert event.error == billing_service.CREDIT_FULFILLMENT_RETRYABLE_ERROR


@pytest.mark.asyncio
async def test_same_stripe_payment_never_grants_credits_twice(monkeypatch, tmp_path):
    monkeypatch.setattr(
        credit_service,
        "_sync_workspace_credit_projection",
        AsyncMock(),
    )
    async with _isolated_legacy_database(tmp_path, "legacy_payment_idempotency") as sessions:
        async with sessions() as db:
            user = User(
                email="legacy-idempotent@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Legacy Idempotent",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            payload = _legacy_credit_checkout(
                user.id,
                session_id="cs_same_stripe_payment",
            )

            first = await handle_stripe_webhook(
                "evt_same_payment_first",
                "checkout.session.completed",
                payload,
                db,
            )
            second = await handle_stripe_webhook(
                "evt_same_payment_second",
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            event_count = await db.scalar(
                select(func.count()).select_from(WebhookEvent)
            )
            assert first["status"] == "processed"
            assert second["status"] == "processed"
            assert user.credits == CREDIT_PACK_SIZE
            assert ledger_count == 1
            assert event_count == 2


@pytest.mark.asyncio
async def test_unconfirmed_payment_never_grants_credits(monkeypatch, tmp_path):
    line_items = AsyncMock(
        return_value={
            "data": [{"price": {"id": CREDIT_PRICE_ID}, "quantity": 1}]
        }
    )
    monkeypatch.setattr(billing_service, "retrieve_credit_line_items", line_items)
    async with _isolated_legacy_database(tmp_path, "legacy_unconfirmed_payment") as sessions:
        async with sessions() as db:
            user = User(
                email="legacy-unconfirmed@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Legacy Unconfirmed",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            payload = _legacy_credit_checkout(
                user.id,
                session_id="cs_unconfirmed_payment",
                payment_status="unpaid",
            )

            result = await handle_stripe_webhook(
                "evt_unconfirmed_payment",
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            assert result["status"] == "rejected"
            assert user.credits == 0
            assert ledger_count == 0
            line_items.assert_awaited_once_with("cs_unconfirmed_payment")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "checkout_overrides", "line_item"),
    [
        pytest.param(
            "negative_metadata",
            {"credits": -CREDIT_PACK_SIZE},
            {"price": {"id": CREDIT_PRICE_ID}, "quantity": 1},
            id="negative-credit-metadata",
        ),
        pytest.param(
            "unbounded_metadata",
            {"credits": 2_500_000},
            {"price": {"id": CREDIT_PRICE_ID}, "quantity": 1},
            id="unbounded-credit-metadata",
        ),
        pytest.param(
            "zero_amount",
            {"amount_total": 0},
            {"price": {"id": CREDIT_PRICE_ID}, "quantity": 1},
            id="zero-payment-amount",
        ),
        pytest.param(
            "wrong_price",
            {},
            {"price": {"id": "price_not_configured"}, "quantity": 1},
            id="untrusted-price",
        ),
        pytest.param(
            "coerced_quantity",
            {},
            {"price": {"id": CREDIT_PRICE_ID}, "quantity": "1"},
            id="no-permissive-quantity-coercion",
        ),
        pytest.param(
            "unbounded_quantity",
            {"credits": 101 * CREDIT_PACK_SIZE},
            {"price": {"id": CREDIT_PRICE_ID}, "quantity": 101},
            id="unbounded-pack-quantity",
        ),
    ],
)
async def test_invalid_credit_contract_fails_closed(
    monkeypatch,
    tmp_path,
    case_name,
    checkout_overrides,
    line_item,
):
    monkeypatch.setattr(
        billing_service,
        "retrieve_credit_line_items",
        AsyncMock(return_value={"data": [line_item]}),
    )
    async with _isolated_legacy_database(
        tmp_path,
        f"legacy_invalid_credit_{case_name}",
    ) as sessions:
        async with sessions() as db:
            user = User(
                email=f"legacy-{case_name}@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Legacy Invalid Credit",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            payload = _legacy_credit_checkout(
                user.id,
                session_id=f"cs_invalid_credit_{case_name}",
                **checkout_overrides,
            )

            result = await handle_stripe_webhook(
                f"evt_invalid_credit_{case_name}",
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            assert result["status"] == "rejected"
            assert user.credits == 0
            assert ledger_count == 0


@pytest.mark.asyncio
async def test_legacy_status_failure_rolls_back_then_retry_is_safe(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        credit_service,
        "_sync_workspace_credit_projection",
        AsyncMock(),
    )
    real_update = webhook_handler_service.update_webhook_status
    update_attempts = 0

    async def fail_first_final_status(*args, **kwargs):
        nonlocal update_attempts
        update_attempts += 1
        if update_attempts == 1:
            raise OperationalError(
                "UPDATE webhook_events",
                {},
                RuntimeError("final status unavailable"),
            )
        return await real_update(*args, **kwargs)

    monkeypatch.setattr(
        webhook_handler_service,
        "update_webhook_status",
        fail_first_final_status,
    )

    async with _isolated_legacy_database(tmp_path, "legacy_atomic_retry") as sessions:
        async with sessions() as db:
            user = User(
                email="legacy-retry@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Legacy Retry",
                credits=0,
                stripe_customer_id="cus_legacy",
            )
            db.add(user)
            await db.commit()
            user_id = user.id
            payload = _legacy_credit_checkout(user_id, session_id="cs_legacy_retry")

            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    "evt_legacy_retry",
                    "checkout.session.completed",
                    payload,
                    db,
                )

            await db.refresh(user)
            ledger_after_failure = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            retryable = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_legacy_retry"
                )
            )
            assert user.credits == 0
            assert ledger_after_failure == 0
            assert retryable is not None
            assert retryable.status == "retryable_failure"

            retry = await handle_stripe_webhook(
                "evt_legacy_retry",
                "checkout.session.completed",
                payload,
                db,
            )
            duplicate = await handle_stripe_webhook(
                "evt_legacy_retry",
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            await db.refresh(retryable)
            ledger_after_retry = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            assert retry["status"] == "processed"
            assert duplicate["status"] == "duplicate"
            assert user.credits == 25
            assert ledger_after_retry == 1
            assert retryable.status == "processed"
            assert retryable.attempt_count == 2


@pytest.mark.asyncio
async def test_unsupported_module_retry_never_provisions(tmp_path):
    async with _isolated_legacy_database(tmp_path, "legacy_module_retry") as sessions:
        async with sessions() as db:
            user = User(
                email="legacy-module@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Legacy Module",
                credits=0,
            )
            db.add(user)
            await db.commit()
            payload = _legacy_module_checkout(
                user.id,
                session_id="cs_legacy_module_retry",
            )

            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    "evt_legacy_module_retry",
                    "checkout.session.completed",
                    payload,
                    db,
                )

            modules_after_failure = await db.scalar(
                select(func.count()).select_from(UserModule)
            )
            ledger_after_failure = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            event = await db.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == "evt_legacy_module_retry"
                )
            )
            await db.refresh(user)

            assert modules_after_failure == 0
            assert ledger_after_failure == 0
            assert user.stripe_customer_id is None
            assert event is not None and event.status == "retryable_failure"
            assert event.attempt_count == 1
            assert event.error == billing_service.MODULE_FULFILLMENT_RETRYABLE_ERROR

            with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
                await handle_stripe_webhook(
                    "evt_legacy_module_retry",
                    "checkout.session.completed",
                    payload,
                    db,
                )

            modules = list((await db.execute(select(UserModule))).scalars())
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            await db.refresh(event)
            await db.refresh(user)

            assert modules == []
            assert ledger_count == 0
            assert user.stripe_customer_id is None
            assert event.status == "retryable_failure"
            assert event.attempt_count == 2
            assert event.error == billing_service.MODULE_FULFILLMENT_RETRYABLE_ERROR


@pytest.mark.asyncio
async def test_paid_unsupported_addon_never_grants_value(
    monkeypatch,
    tmp_path,
):
    checkout_type = "addon"
    processor = AsyncMock(side_effect=AssertionError("Unsupported fulfillment ran"))
    monkeypatch.setattr(billing_service, "handle_checkout_completed", processor)

    async with _isolated_legacy_database(
        tmp_path,
        f"unsupported_checkout_{checkout_type}",
    ) as sessions:
        async with sessions() as db:
            user = User(
                email=f"unsupported-{checkout_type}@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Unsupported Checkout",
                credits=0,
            )
            db.add(user)
            await db.commit()
            payload = {
                "id": f"cs_unsupported_{checkout_type}",
                "mode": "payment",
                "payment_status": "paid",
                "customer": f"cus_unsupported_{checkout_type}",
                "client_reference_id": str(user.id),
                "metadata": {"type": checkout_type},
            }

            first = await handle_stripe_webhook(
                f"evt_unsupported_{checkout_type}",
                "checkout.session.completed",
                payload,
                db,
            )
            duplicate = await handle_stripe_webhook(
                f"evt_unsupported_{checkout_type}",
                "checkout.session.completed",
                payload,
                db,
            )
            second_event = await handle_stripe_webhook(
                f"evt_unsupported_{checkout_type}_second",
                "checkout.session.completed",
                payload,
                db,
            )

            await db.refresh(user)
            module_count = await db.scalar(
                select(func.count()).select_from(UserModule)
            )
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            events = list((await db.execute(select(WebhookEvent))).scalars())

            assert first["status"] == "rejected"
            assert duplicate["status"] == "duplicate"
            assert second_event["status"] == "rejected"
            assert user.stripe_customer_id is None
            assert user.credits == 0
            assert module_count == 0
            assert ledger_count == 0
            assert len(events) == 2
            assert all(event.status == "rejected" for event in events)
            processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_distinct_paid_module_events_for_same_session_remain_retryable(
    monkeypatch,
    tmp_path,
):
    processor = AsyncMock(side_effect=AssertionError("Module fulfillment ran"))
    monkeypatch.setattr(billing_service, "handle_checkout_completed", processor)

    async with _isolated_legacy_database(
        tmp_path,
        "unsupported_module_same_session",
    ) as sessions:
        async with sessions() as db:
            user = User(
                email="unsupported-module@example.com",
                password_hash="not-a-real-password-hash",
                full_name="Unsupported Module Checkout",
                credits=0,
            )
            db.add(user)
            await db.commit()
            payload = _legacy_module_checkout(
                user.id,
                session_id="cs_unsupported_module_shared",
            )

            for event_id in (
                "evt_unsupported_module_first",
                "evt_unsupported_module_first",
                "evt_unsupported_module_second",
            ):
                with pytest.raises(
                    webhook_handler_service.WebhookProcessingUnavailable
                ):
                    await handle_stripe_webhook(
                        event_id,
                        "checkout.session.completed",
                        payload,
                        db,
                    )

            await db.refresh(user)
            module_count = await db.scalar(
                select(func.count()).select_from(UserModule)
            )
            ledger_count = await db.scalar(
                select(func.count()).select_from(CreditLedger)
            )
            events = list(
                (
                    await db.execute(
                        select(WebhookEvent).order_by(WebhookEvent.stripe_event_id)
                    )
                ).scalars()
            )

            assert user.stripe_customer_id is None
            assert user.credits == 0
            assert module_count == 0
            assert ledger_count == 0
            assert [event.status for event in events] == [
                "retryable_failure",
                "retryable_failure",
            ]
            assert [event.attempt_count for event in events] == [2, 1]
            assert {event.error for event in events} == {
                billing_service.MODULE_FULFILLMENT_RETRYABLE_ERROR
            }
            processor.assert_not_awaited()


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
