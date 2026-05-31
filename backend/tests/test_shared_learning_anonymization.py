from __future__ import annotations


def test_shared_learning_is_anonymized(ai_client, admin_auth_headers) -> None:
    response = ai_client.post(
        "/admin/ai/learning/extract",
        json={
            "source_scope": "tenant",
            "tenant_id": "tenant_redacted",
            "content": "Contact me at client@example.com with key sk_live_secret and account acct_98765",
            "category": "billing",
            "master_context": True,
        },
        headers=admin_auth_headers(),
    )

    assert response.status_code == 200
    insight = response.json()["insight"]
    assert "client@example.com" not in insight
    assert "sk_live_secret" not in insight
    assert "acct_98765" not in insight
    assert "[redacted-email]" in insight
    assert "[redacted-secret]" in insight
    assert response.json()["tenant_id"] is None
