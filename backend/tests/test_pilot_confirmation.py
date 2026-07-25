"""Public Pilot confirmation state derived only from persisted payments."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.database import Base
from api.models.pilot import PilotPayment, PilotRequest
from api.routers import billing as billing_router


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


def _payment(*, session_id: str, status: str) -> PilotPayment:
    return PilotPayment(
        id=uuid.uuid4(),
        pilot_request_id=None,
        stripe_checkout_session_id=session_id,
        stripe_payment_intent_id=f"pi_{session_id}",
        stripe_event_id=f"evt_{session_id}",
        stripe_payment_link_id="plink_pilot",
        stripe_price_id="price_pilot",
        customer_email="must-not-leak@example.com",
        currency="cad",
        amount_subtotal=29700,
        payment_status="paid" if status == "paid" else "unpaid",
        status=status,
        livemode=False,
    )


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
            db.add(_payment(session_id=session_id, status=payment_status))
            await db.commit()

            response = await billing_router.get_pilot_confirmation(
                db,
                session_id=session_id,
            )

            assert response.model_dump() == {"status": public_status}
            assert "email" not in response.model_dump_json()
            assert "stripe" not in response.model_dump_json()
            assert session_id not in response.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session_id",
    [
        pytest.param(None, id="absent"),
        pytest.param("", id="empty"),
        pytest.param("not-a-checkout-session", id="invalid"),
        pytest.param("cs_unknown", id="unknown"),
    ],
)
async def test_query_parameter_alone_never_confirms(
    monkeypatch,
    tmp_path,
    session_id,
):
    stripe_retrieve = MagicMock(
        side_effect=AssertionError("Confirmation must never call Stripe")
    )
    monkeypatch.setattr(
        billing_router.stripe.checkout.Session,
        "retrieve",
        stripe_retrieve,
        raising=False,
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
