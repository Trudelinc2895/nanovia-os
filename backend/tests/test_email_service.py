from types import SimpleNamespace

import pytest

from api.config import settings
from api.services import email_service


@pytest.mark.asyncio
async def test_send_forwards_reply_to_and_idempotency_key(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, json, headers):
            captured.update(url=url, json=json, headers=headers)
            return SimpleNamespace(
                is_success=True,
                status_code=200,
                text="",
                json=lambda: {"id": "email_test"},
            )

    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email_service.httpx, "AsyncClient", FakeClient)

    sent = await email_service._send(
        "operator@nanovia.ca",
        "Pilot",
        "<p>Ready</p>",
        reply_to="client@example.com",
        idempotency_key="pilot-intake-operator/request-123",
    )

    assert sent is True
    assert captured["json"]["reply_to"] == "client@example.com"
    assert captured["headers"]["Idempotency-Key"] == "pilot-intake-operator/request-123"
    assert captured["headers"]["Authorization"] == "Bearer re_test"
