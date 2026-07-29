"""Public Pilot confirmation state derived only from persisted payments."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import stripe
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.database import Base
from api.models.pilot import PilotPayment, PilotRequest
from api.routers import billing as billing_router


PAYMENT_LINK_ID = "plink_pilot"
PRICE_ID = "price_pilot"


@pytest.fixture(autouse=True)
def _pilot_settings(monkeypatch):
    monkeypatch.setattr(billing_router.settings, "APP_ENV", "test")
    monkeypatch.setattr(
        billing_router.settings,
        "STRIPE_PILOT_PAYMENT_LINK_ID",
        PAYMENT_LINK_ID,
    )
    monkeypatch.setattr(
        billing_router.settings,
        "STRIPE_PILOT_PRICE_ID",
        PRICE_ID,
    )


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
            ],
        )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        await engine.dispose()


def _request(*, request_id: uuid.UUID | None = None) -> PilotRequest:
    return PilotRequest(
        id=request_id or uuid.uuid4(),
        name="Client Pilot",
        email="client@example.com",
        subject="demo",
        message="Automatiser une tâche répétitive.",
        status="pending",
        notification_status="sent",
    )


def _payment(
    *,
    request: PilotRequest,
    session_id: str,
    status: str,
) -> PilotPayment:
    return PilotPayment(
        id=uuid.uuid4(),
        pilot_request_id=request.id,
        stripe_checkout_session_id=session_id,
        stripe_payment_intent_id=f"pi_{session_id}",
        stripe_event_id=f"evt_{session_id}",
        stripe_payment_link_id=PAYMENT_LINK_ID,
        stripe_price_id=PRICE_ID,
        customer_email="must-not-leak@example.com",
        currency="cad",
        amount_subtotal=29700,
        payment_status="paid" if status == "paid" else "unpaid",
        status=status,
        livemode=False,
    )


def _stripe_session(
    *,
    session_id: str,
    request_id: uuid.UUID,
    payment_status: str = "paid",
    payment_link: str = PAYMENT_LINK_ID,
) -> dict:
    return {
        "id": session_id,
        "client_reference_id": str(request_id),
        "payment_link": payment_link,
        "mode": "payment",
        "livemode": False,
        "currency": "cad",
        "payment_status": payment_status,
    }


def _install_stripe_session(monkeypatch, session: dict) -> AsyncMock:
    retrieve = AsyncMock(return_value=session)
    monkeypatch.setattr(
        billing_router,
        "_retrieve_pilot_checkout_session",
        retrieve,
    )
    return retrieve


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payment_status", "public_status"),
    [
        pytest.param("paid", "confirmed", id="confirmed"),
        pytest.param("processing", "processing", id="processing"),
        pytest.param("manual_review", "manual_review", id="manual-review"),
        pytest.param("failed", "manual_review", id="failed-is-manual-review"),
    ],
)
async def test_confirmation_returns_only_public_persisted_state(
    monkeypatch,
    tmp_path,
    payment_status,
    public_status,
):
    async with _isolated_database(
        tmp_path,
        f"confirmation_{payment_status}",
    ) as sessions:
        async with sessions() as db:
            session_id = f"cs_{payment_status}"
            request = _request()
            db.add(request)
            db.add(
                _payment(
                    request=request,
                    session_id=session_id,
                    status=payment_status,
                )
            )
            await db.commit()
            _install_stripe_session(
                monkeypatch,
                _stripe_session(session_id=session_id, request_id=request.id),
            )

            response = await billing_router.get_pilot_confirmation(
                db,
                session_id=session_id,
            )

            assert response.model_dump() == {"status": public_status}
            assert "email" not in response.model_dump_json()
            assert "stripe" not in response.model_dump_json()
            assert session_id not in response.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", [None, "", "not-a-checkout-session"])
async def test_invalid_query_parameter_never_calls_stripe(
    monkeypatch,
    tmp_path,
    session_id,
):
    stripe_retrieve = AsyncMock(
        side_effect=AssertionError("Invalid session ids must not call Stripe")
    )
    monkeypatch.setattr(
        billing_router,
        "_retrieve_pilot_checkout_session",
        stripe_retrieve,
    )

    async with _isolated_database(tmp_path, "unknown_confirmation") as sessions:
        async with sessions() as db:
            response = await billing_router.get_pilot_confirmation(
                db,
                session_id=session_id,
            )
            payment_count = await db.scalar(
                select(func.count()).select_from(PilotPayment)
            )

            assert response.model_dump() == {"status": "manual_review"}
            assert payment_count == 0
            stripe_retrieve.assert_not_called()


@pytest.mark.asyncio
async def test_redirect_before_webhook_retries_then_confirms_without_provisioning(
    monkeypatch,
    tmp_path,
):
    session_id = "cs_redirect_race"
    async with _isolated_database(tmp_path, "redirect_race") as sessions:
        async with sessions() as db:
            request = _request()
            db.add(request)
            await db.commit()
            retrieve = _install_stripe_session(
                monkeypatch,
                _stripe_session(session_id=session_id, request_id=request.id),
            )

            pending = await billing_router.get_pilot_confirmation(
                db,
                session_id=session_id,
            )
            assert pending.model_dump() == {"status": "processing"}
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 0

            db.add(_payment(request=request, session_id=session_id, status="paid"))
            request.status = "paid"
            await db.commit()

            confirmed = await billing_router.get_pilot_confirmation(
                db,
                session_id=session_id,
            )
            repeated = await billing_router.get_pilot_confirmation(
                db,
                session_id=session_id,
            )

            assert confirmed.model_dump() == {"status": "confirmed"}
            assert repeated.model_dump() == {"status": "confirmed"}
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 1
            assert retrieve.await_count == 3


@pytest.mark.asyncio
async def test_incomplete_verified_payment_remains_processing(monkeypatch, tmp_path):
    session_id = "cs_incomplete"
    async with _isolated_database(tmp_path, "incomplete") as sessions:
        async with sessions() as db:
            request = _request()
            db.add(request)
            await db.commit()
            _install_stripe_session(
                monkeypatch,
                _stripe_session(
                    session_id=session_id,
                    request_id=request.id,
                    payment_status="unpaid",
                ),
            )

            response = await billing_router.get_pilot_confirmation(
                db,
                session_id=session_id,
            )

            assert response.model_dump() == {"status": "processing"}
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 0


@pytest.mark.asyncio
async def test_forged_or_unrelated_session_never_confirms(monkeypatch, tmp_path):
    session_id = "cs_forged"
    retrieve = AsyncMock(
        side_effect=stripe.error.InvalidRequestError("No such session", "id")
    )
    monkeypatch.setattr(
        billing_router,
        "_retrieve_pilot_checkout_session",
        retrieve,
    )

    async with _isolated_database(tmp_path, "forged") as sessions:
        async with sessions() as db:
            response = await billing_router.get_pilot_confirmation(
                db,
                session_id=session_id,
            )

            assert response.model_dump() == {"status": "manual_review"}
            assert await db.scalar(select(func.count()).select_from(PilotPayment)) == 0


@pytest.mark.asyncio
async def test_session_for_another_request_never_leaks_confirmation(
    monkeypatch,
    tmp_path,
):
    session_id = "cs_other_request"
    async with _isolated_database(tmp_path, "other_request") as sessions:
        async with sessions() as db:
            stored_request = _request()
            stripe_request = _request()
            db.add_all([stored_request, stripe_request])
            db.add(
                _payment(
                    request=stored_request,
                    session_id=session_id,
                    status="paid",
                )
            )
            await db.commit()
            _install_stripe_session(
                monkeypatch,
                _stripe_session(
                    session_id=session_id,
                    request_id=stripe_request.id,
                ),
            )

            response = await billing_router.get_pilot_confirmation(
                db,
                session_id=session_id,
            )

            assert response.model_dump() == {"status": "manual_review"}
            assert "email" not in response.model_dump_json()
            assert session_id not in response.model_dump_json()
