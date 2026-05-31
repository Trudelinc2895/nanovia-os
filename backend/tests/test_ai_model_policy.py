from __future__ import annotations

from api.config import settings
from api.services import model_policy, sandbox_service


def test_model_policy_selects_models_by_plan(ai_client) -> None:
    assert model_policy.select_model("starter") == "gpt-5.4-mini"
    assert model_policy.select_model("business") == "gpt-5.4"
    assert model_policy.select_model("owner") == "gpt-5.5"


def test_sandbox_rejects_live_keys_for_ai(ai_client, monkeypatch, tenant_auth_headers) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "sandbox")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_123", raising=False)

    response = ai_client.post(
        "/ai/tenant/chat",
        json={
            "tenant_id": "sandbox_workspace",
            "workspace_id": "sandbox_workspace",
            "user_id": "u4",
            "message": "Help me in sandbox",
        },
        headers=tenant_auth_headers(user_id="u4", workspace_id="sandbox_workspace", tenant_id="sandbox_workspace"),
    )

    assert response.status_code == 409
