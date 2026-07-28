"""Focused tests for the public Nanovia Pro Pilot contact endpoint."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.models.pilot import PilotRequest
from api.routers import contact


def _request(client_host: str = "127.0.0.1") -> Request:
    return Request({"type": "http", "client": (client_host, 12345)})


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
async def test_contact_log_sanitizes_client_address_and_omits_form_content(
    monkeypatch,
    tmp_path,
    caplog,
):
    async def fake_send_email(*, to: str, subject: str, html: str) -> bool:
        return True

    monkeypatch.setattr(contact, "send_email", fake_send_email)
    db, engine = await _isolated_session(tmp_path)
    try:
        with caplog.at_level(logging.INFO, logger=contact.__name__):
            await contact.contact_form(
                _body(
                    name="Client\r\nFORGED_NAME",
                    email="private@example.com",
                    message="Message légitime.\r\nFORGED_FORM_CONTENT",
                ),
                _request("203.0.113.10\r\nFORGED_LOG_RECORD"),
                db,
            )

        messages = [
            record.getMessage()
            for record in caplog.records
            if record.name == contact.__name__
        ]
        assert len(messages) == 1
        assert all("\r" not in message and "\n" not in message for message in messages)
        assert all("private@example.com" not in message for message in messages)
        assert all("FORGED_NAME" not in message for message in messages)
        assert all("FORGED_FORM_CONTENT" not in message for message in messages)
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
