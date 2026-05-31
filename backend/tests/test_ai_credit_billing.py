from __future__ import annotations

from api.services import sandbox_service


def test_tenant_ai_blocked_when_credits_are_insufficient(ai_client, tenant_auth_headers) -> None:
    sandbox_service.adjust_workspace_credits("sandbox_workspace", -100000, actor="tester", reason="force insufficient credits")

    response = ai_client.post(
        "/ai/tenant/chat",
        json={
            "tenant_id": "sandbox_workspace",
            "workspace_id": "sandbox_workspace",
            "user_id": "u2",
            "message": "Run a costly task",
        },
        headers=tenant_auth_headers(user_id="u2", workspace_id="sandbox_workspace", tenant_id="sandbox_workspace"),
    )

    assert response.status_code == 409


def test_tenant_ai_blocked_when_subscription_inactive(ai_client, tenant_auth_headers) -> None:
    store = sandbox_service._load_workspace_store()
    for item in store["workspaces"]:
        if item["id"] == "sandbox_workspace":
            item["subscription_status"] = "canceled"
    sandbox_service._save_workspace_store(store)

    response = ai_client.post(
        "/ai/tenant/chat",
        json={
            "tenant_id": "sandbox_workspace",
            "workspace_id": "sandbox_workspace",
            "user_id": "u3",
            "message": "Answer customer",
        },
        headers=tenant_auth_headers(user_id="u3", workspace_id="sandbox_workspace", tenant_id="sandbox_workspace"),
    )

    assert response.status_code == 403
