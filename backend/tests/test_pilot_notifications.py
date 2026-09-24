"""Focused tests for durable Nanovia Pro Pilot notifications."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.models.pilot import PilotPayment, PilotRequest
from api.services import pilot_notification_service as notifications


def _request(**overrides) -> PilotRequest:
    values = {
        "id": uuid.uuid4(),
        "name": "Client <script>alert(1)</script>",
        "email": "client@example.com",
        "subject": "demo",
        "message": "Une tâche répétitive suffisamment détaillée.",
        "company": "Entreprise Pilot",
        "business_type": "Services professionnels",
        "repetitive_task": "Répondre aux demandes entrantes.",
        "examples": "Un exemple anonymisé.",
        "goal": "Réduire le délai de réponse.",
        "urgency": "eleve",
        "status": "pending",
        "fulfillment_status": "new",
        "notification_status": "pending",
        "client_notification_status": "pending",
        "payment_notification_status": "pending",
        "notification_attempts": 0,
        "payment_notification_attempts": 0,
    }
    values.update(overrides)
    return PilotRequest(**values)


@pytest.mark.asyncio
async def test_intake_notifications_are_escaped_routed_and_idempotent(monkeypatch):
    sent: list[dict[str, object]] = []

    async def fake_send_email(**kwargs) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr(notifications, "send_email", fake_send_email)
    monkeypatch.setattr(
        notifications.settings,
        "CONTACT_RECIPIENT_EMAIL",
        "operations@nanovia.ca",
    )
    request = _request()

    result = await notifications.deliver_intake_notifications(request)

    assert result == {"operator": True, "client": True}
    assert request.routed_to == "operations@nanovia.ca"
    assert request.notification_status == "sent"
    assert request.client_notification_status == "sent"
    assert request.notification_attempts == 1
    assert len(sent) == 2
    assert sent[0]["to"] == "operations@nanovia.ca"
    assert sent[0]["reply_to"] == "client@example.com"
    assert sent[0]["idempotency_key"] == f"pilot-intake-operator/{request.id}"
    assert "<script>" not in str(sent[0]["html"])
    assert "&lt;script&gt;" in str(sent[0]["html"])
    assert sent[1]["to"] == "client@example.com"
    assert sent[1]["idempotency_key"] == f"pilot-intake-client/{request.id}"


@pytest.mark.asyncio
async def test_failed_intake_can_retry_without_changing_idempotency_keys(monkeypatch):
    attempts: list[str] = []
    succeeds = False

    async def fake_send_email(**kwargs) -> bool:
        attempts.append(str(kwargs["idempotency_key"]))
        return succeeds

    monkeypatch.setattr(notifications, "send_email", fake_send_email)
    monkeypatch.setattr(
        notifications.settings,
        "CONTACT_RECIPIENT_EMAIL",
        "operations@nanovia.ca",
    )
    request = _request()

    await notifications.deliver_intake_notifications(request)
    assert request.notification_status == "failed"
    assert request.client_notification_status == "failed"

    succeeds = True
    await notifications.deliver_intake_notifications(request)

    assert request.notification_status == "sent"
    assert request.client_notification_status == "sent"
    assert request.notification_attempts == 2
    assert attempts[:2] == attempts[2:]


@pytest.mark.asyncio
async def test_paid_request_is_qualified_and_notifies_both_sides(monkeypatch):
    sent: list[str] = []
    client_html: list[str] = []

    async def fake_send_email(**kwargs) -> bool:
        sent.append(str(kwargs["idempotency_key"]))
        if kwargs["to"] == "client@example.com":
            client_html.append(kwargs["html"])
        return True

    monkeypatch.setattr(notifications, "send_email", fake_send_email)
    monkeypatch.setattr(
        notifications.settings,
        "CONTACT_RECIPIENT_EMAIL",
        "operations@nanovia.ca",
    )
    request = _request(status="paid")
    payment = PilotPayment(
        pilot_request_id=request.id,
        amount_subtotal=35_000,
        currency="cad",
        status="paid",
        payment_status="paid",
    )
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: payment)

    delivered = await notifications.deliver_payment_notifications(request, db)

    assert delivered is True
    assert request.payment_notification_status == "sent"
    assert request.payment_notification_attempts == 1
    assert request.fulfillment_status == "qualified"
    assert "350,00 $ CAD" in client_html[0]
    assert "297" not in client_html[0]
    assert sent == [
        f"pilot-paid-operator/{request.id}",
        f"pilot-paid-client/{request.id}",
    ]


@pytest.mark.asyncio
async def test_payment_notification_without_a_paid_record_does_not_claim_delivery(monkeypatch):
    send = AsyncMock(side_effect=AssertionError("No verified payment to announce"))
    monkeypatch.setattr(notifications, "send_email", send)
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
    request = _request(status="paid")

    assert await notifications.deliver_payment_notifications(request, db) is False
    assert request.payment_notification_status == "failed"
    send.assert_not_awaited()
