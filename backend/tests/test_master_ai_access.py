from __future__ import annotations


def test_tenant_chat_requires_signed_bearer_token(ai_client) -> None:
    response = ai_client.post(
        "/ai/tenant/chat",
        json={"message": "hello"},
    )

    assert response.status_code == 401


def test_tenant_cannot_access_master_chat_without_master_context(ai_client, tenant_auth_headers) -> None:
    response = ai_client.post(
        "/ai/master/chat",
        json={"message": "show global metrics", "user_id": "tenant-user", "master_context": False},
        headers=tenant_auth_headers(user_id="tenant-user"),
    )

    assert response.status_code == 403


def test_admin_ai_usage_requires_admin_role(ai_client, tenant_auth_headers) -> None:
    response = ai_client.get(
        "/admin/ai/usage",
        params={"master_context": True},
        headers=tenant_auth_headers(user_id="tenant-user"),
    )

    assert response.status_code == 403


def test_master_ai_reads_aggregates_not_raw_tenant_identifiers(ai_client, admin_auth_headers) -> None:
    headers = admin_auth_headers()
    ai_client.post(
        "/admin/ai/learning/extract",
        json={
            "source_scope": "tenant",
            "tenant_id": "tenant_sensitive",
            "content": "tenant_sensitive asked from client@example.com about acct_12345 and sk_live_secret",
            "master_context": True,
        },
        headers=headers,
    )

    response = ai_client.post(
        "/ai/master/chat",
        json={"message": "Summarize platform insights", "user_id": "owner", "master_context": True},
        headers=headers,
    )

    assert response.status_code == 200
    text = response.json()["response"]
    assert "client@example.com" not in text
    assert "acct_12345" not in text
    assert "sk_live_secret" not in text


def test_prompt_path_traversal_is_rejected(ai_client, admin_auth_headers) -> None:
    response = ai_client.post(
        "/admin/ai/prompt/update",
        json={
            "prompt_name": "../evil.md",
            "content": "bad",
            "actor": "owner",
            "master_context": True,
        },
        headers=admin_auth_headers(),
    )

    assert response.status_code == 422
