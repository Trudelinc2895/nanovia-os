from __future__ import annotations

from api.services import sandbox_service


def test_tenant_ai_usage_debits_credits(ai_client, tenant_auth_headers) -> None:
    before = sandbox_service.get_credits("sandbox_workspace")

    response = ai_client.post(
        "/ai/tenant/chat",
        json={
            "tenant_id": "sandbox_workspace",
            "workspace_id": "sandbox_workspace",
            "user_id": "usage-user",
            "message": "Prepare a billing response",
        },
        headers=tenant_auth_headers(user_id="usage-user", workspace_id="sandbox_workspace", tenant_id="sandbox_workspace"),
    )

    assert response.status_code == 200
    after = sandbox_service.get_credits("sandbox_workspace")
    assert after["remaining"] < before["remaining"]
    assert response.json()["usage"]["credits_charged"] >= 1
