from __future__ import annotations

from api.services import ai_service


def test_tenant_memory_isolation(ai_client, tenant_auth_headers) -> None:
    headers = tenant_auth_headers(tenant_id="tenant_a")
    ai_client.post(
        "/ai/memory/save",
        json={"scope": "tenant", "tenant_id": "tenant_a", "content": "private note for A"},
        headers=headers,
    )

    tenant_a = ai_client.get("/ai/memory/search", params={"scope": "tenant", "tenant_id": "tenant_a", "query": "private"}, headers=headers).json()
    tenant_b = ai_client.get("/ai/memory/search", params={"scope": "tenant", "tenant_id": "tenant_b", "query": "private"}, headers=headers)

    assert len(tenant_a["items"]) == 1
    assert tenant_b.status_code == 403


def test_tenant_prompt_contains_only_allowed_modules(ai_client, tenant_auth_headers) -> None:
    payload = {
        "tenant_id": "sandbox_pro",
        "workspace_id": "sandbox_pro",
        "user_id": "u1",
        "message": "Show me my enabled capabilities",
    }

    response = ai_client.post("/ai/tenant/chat", json=payload, headers=tenant_auth_headers(user_id="u1", workspace_id="sandbox_pro", tenant_id="sandbox_pro"))

    assert response.status_code == 200
    profile = ai_service.get_profile("sandbox_pro", "sandbox_pro")
    assert profile is not None
    for module in profile["allowed_modules"]:
        assert module in response.json()["response"]
    assert "super_admin_tools" not in response.json()["response"]


def test_tenant_path_traversal_is_rejected(ai_client, tenant_auth_headers) -> None:
    response = ai_client.post(
        "/ai/tenant/chat",
        json={
            "tenant_id": "..\\evil",
            "workspace_id": "sandbox_workspace",
            "user_id": "u5",
            "message": "noop",
        },
        headers=tenant_auth_headers(user_id="u5", workspace_id="sandbox_workspace", tenant_id="sandbox_workspace"),
    )

    assert response.status_code == 422
