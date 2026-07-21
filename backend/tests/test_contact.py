"""Focused tests for the public Nanovia Pro Pilot contact endpoint."""
from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from api.routers import contact


def _request() -> Request:
    return Request({"type": "http", "client": ("127.0.0.1", 12345)})


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
async def test_contact_confirms_only_after_delivery_and_escapes_html(monkeypatch):
    sent: dict[str, str] = {}

    async def fake_send_email(*, to: str, subject: str, html: str) -> bool:
        sent.update(to=to, subject=subject, html=html)
        return True

    monkeypatch.setattr(contact, "send_email", fake_send_email)

    response = await contact.contact_form(
        _body(name="Client <script>alert(1)</script>"),
        _request(),
    )

    assert response["received"] is True
    assert sent["to"] == contact.settings.CONTACT_RECIPIENT_EMAIL
    assert "<script>" not in sent["html"]
    assert "&lt;script&gt;" in sent["html"]
    assert "127.0.0.1" not in sent["html"]


@pytest.mark.asyncio
async def test_contact_returns_503_when_delivery_is_unavailable(monkeypatch):
    async def fake_send_email(*, to: str, subject: str, html: str) -> bool:
        return False

    monkeypatch.setattr(contact, "send_email", fake_send_email)

    with pytest.raises(HTTPException) as exc_info:
        await contact.contact_form(_body(), _request())

    assert exc_info.value.status_code == 503
    assert "courriel de secours" in str(exc_info.value.detail)
