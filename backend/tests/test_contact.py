"""Focused tests for the public Nanovia Pro Pilot contact endpoint."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.models.pilot import PilotRequest
from api.routers import contact


def _request() -> Request:
    return Request({"type": "http", "client": ("127.0.0.1", 12345)})


async def _isolated_session(
    tmp_path: Path,
) -> tuple[AsyncSession, object]:
    database_path = (tmp_path / "contact.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(PilotRequest.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return session_factory(), engine


def _body(**overrides: str) -> contact.ContactRequest:
    values = {
        "name": "Client Pilot",
        "email": "client@example.com",
        "subject": "demo",
        "message": "Une tâche répétitive clairement décrite.",
    }
    values.update(overrides)
    return contact.ContactRequest(**values)


@pytest.mark.asyncio
async def test_contact_persists_request_id_and_escapes_html(monkeypatch, tmp_path):
    sent: dict[str, str] = {}

    async def fake_send_email(*, to: str, subject: str, html: str) -> bool:
        sent.update(to=to, subject=subject, html=html)
        return True

    monkeypatch.setattr(contact, "send_email", fake_send_email)
    db, engine = await _isolated_session(tmp_path)
    try:
        response = await contact.contact_form(
            _body(name="Client <script>alert(1)</script>"),
            _request(),
            db,
        )
        stored = (await db.execute(select(PilotRequest))).scalar_one()

        assert response["received"] is True
        assert response["request_id"] == str(stored.id)
        assert response["notification_sent"] is True
        assert stored.notification_status == "sent"
        assert sent["to"] == contact.settings.CONTACT_RECIPIENT_EMAIL
        assert "<script>" not in sent["html"]
        assert "&lt;script&gt;" in sent["html"]
        assert "127.0.0.1" not in sent["html"]
    finally:
        await db.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_contact_persists_when_delivery_is_unavailable(monkeypatch, tmp_path):
    async def fake_send_email(*, to: str, subject: str, html: str) -> bool:
        raise RuntimeError("Resend unavailable")

    monkeypatch.setattr(contact, "send_email", fake_send_email)
    db, engine = await _isolated_session(tmp_path)
    try:
        response = await contact.contact_form(_body(), _request(), db)
        stored = (await db.execute(select(PilotRequest))).scalar_one()

        assert response["received"] is True
        assert response["request_id"] == str(stored.id)
        assert response["notification_sent"] is False
        assert stored.notification_status == "failed"
    finally:
        await db.close()
        await engine.dispose()
