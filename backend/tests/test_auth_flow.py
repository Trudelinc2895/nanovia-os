"""Critical auth integration tests."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet

Path("test_auth.db").unlink(missing_ok=True)

from fastapi.testclient import TestClient

from api import main as main_module
from api.config import settings
from api.main import app


def test_register_sets_refresh_cookie_and_returns_me():
    email = f"{uuid.uuid4()}@example.com"

    with patch("api.routers.auth.ensure_owner_workspace", new=AsyncMock()) as ensure_workspace_mock, TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Prod Ready"},
        )

        assert register.status_code == 201, register.text
        assert "refresh_token=" in (register.headers.get("set-cookie") or "")
        ensure_workspace_mock.assert_awaited()

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {register.json()['access_token']}"},
        )

        assert me.status_code == 200, me.text
        assert me.json()["email"] == email


def test_register_stores_hashed_email_verification_token():
    email = f"{uuid.uuid4()}@example.com"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Protected Verify"},
        )
        assert register.status_code == 201, register.text

        with sqlite3.connect("test_auth.db") as conn:
            stored_token = conn.execute(
                "SELECT email_verification_token FROM users WHERE email = ?",
                (email,),
            ).fetchone()[0]

        assert stored_token.startswith("hmac-sha256:")


def test_mobile_register_device_encrypts_push_token(monkeypatch):
    fake_redis = _FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    previous_key = settings.TOTP_ENCRYPTION_KEY
    monkeypatch.setattr(main_module, "_redis_pool", None)
    monkeypatch.setattr(main_module, "_get_redis", _fake_get_redis)
    monkeypatch.setattr(settings, "TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    email = f"{uuid.uuid4()}@example.com"

    try:
        with TestClient(app) as client:
            register = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "Password1", "full_name": "Push Token Protect"},
            )
            assert register.status_code == 201, register.text
            access_token = register.json()["access_token"]
            response = client.post(
                "/api/v1/notifications/register-device",
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "push_token": "ExponentPushToken[abc123secure]",
                    "device_id": "device-secure-123",
                    "device_name": "iPhone",
                    "platform": "ios",
                },
            )
            assert response.status_code == 201, response.text

            with sqlite3.connect("test_auth.db") as conn:
                stored_token = conn.execute(
                    "SELECT push_token FROM device_sessions WHERE device_id = ?",
                    ("device-secure-123",),
                ).fetchone()[0]

            assert stored_token.startswith("enc::")
            assert stored_token != "ExponentPushToken[abc123secure]"
    finally:
        settings.TOTP_ENCRYPTION_KEY = previous_key


def test_refresh_rotates_refresh_cookie():
    email = f"{uuid.uuid4()}@example.com"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Cookie Rotate"},
        )
        assert register.status_code == 201, register.text

        refreshed = client.post("/api/v1/auth/refresh", json={})

        assert refreshed.status_code == 200, refreshed.text
        assert "refresh_token=" in (refreshed.headers.get("set-cookie") or "")
        assert refreshed.json()["access_token"]


def test_register_login_and_portal_route_exposure():
    email = f"{uuid.uuid4()}@example.com"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Flow Check"},
        )
        assert register.status_code == 201, register.text

        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password1"},
        )
        assert login.status_code == 200, login.text
        assert login.json()["access_token"]

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert me.status_code == 200, me.text
        assert me.json()["email"] == email

        portal = client.post("/api/v1/billing/portal-session")
        assert portal.status_code == 401, portal.text


def test_public_entrypoint_health_exposed():
    with TestClient(app) as client:
        resp = client.get("/api/v1/health/public-entrypoint")
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["raw_ip_supported_for_login"] is False
        assert payload["canonical_web_url"].startswith("https://")


class _FakeRedis:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, seconds: int) -> bool:  # noqa: ARG002
        return True


def test_refresh_rate_limit_kicks_in(monkeypatch):
    fake_redis = _FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(main_module, "_redis_pool", None)
    monkeypatch.setattr(main_module, "_get_redis", _fake_get_redis)
    monkeypatch.setattr(main_module, "_get_load_multiplier", lambda: 1.0)

    email = f"{uuid.uuid4()}@example.com"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Rate Limit"},
        )
        assert register.status_code == 201, register.text

        for _ in range(20):
            refreshed = client.post("/api/v1/auth/refresh", json={})
            assert refreshed.status_code == 200, refreshed.text

        blocked = client.post("/api/v1/auth/refresh", json={})
        assert blocked.status_code == 429, blocked.text
        assert "60 secondes" in blocked.json()["detail"]


def test_admin_route_requires_allowed_ip_in_production(monkeypatch):
    previous_env = settings.APP_ENV
    previous_ips_raw = settings.ADMIN_ALLOWED_IPS_RAW

    fake_redis = _FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(main_module, "_redis_pool", None)
    monkeypatch.setattr(main_module, "_get_redis", _fake_get_redis)
    email = f"{uuid.uuid4()}@example.com"

    try:
        with TestClient(app) as client:
            monkeypatch.setattr(settings, "APP_ENV", "production")
            monkeypatch.setattr(settings, "ADMIN_ALLOWED_IPS_RAW", "203.0.113.10/32")
            register = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "Password1", "full_name": "Admin Guard"},
            )
            assert register.status_code == 201, register.text
            access_token = register.json()["access_token"]

            with sqlite3.connect("test_auth.db") as conn:
                conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
                conn.commit()

            denied = client.get(
                "/api/v1/admin/users",
                headers={"Authorization": f"Bearer {access_token}", "X-Forwarded-For": "198.51.100.20"},
            )
            assert denied.status_code == 403, denied.text
            assert denied.json()["detail"] == "Admin network access required"

            allowed = client.get(
                "/api/v1/admin/users",
                headers={"Authorization": f"Bearer {access_token}", "X-Forwarded-For": "203.0.113.10"},
            )
            assert allowed.status_code == 200, allowed.text
    finally:
        settings.APP_ENV = previous_env
        settings.ADMIN_ALLOWED_IPS_RAW = previous_ips_raw


def test_admin_workspace_routes_expose_and_block_workspace(monkeypatch):
    fake_redis = _FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(main_module, "_redis_pool", None)
    monkeypatch.setattr(main_module, "_get_redis", _fake_get_redis)
    email = f"{uuid.uuid4()}@example.com"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Workspace Admin"},
        )
        assert register.status_code == 201, register.text
        access_token = register.json()["access_token"]

        with sqlite3.connect("test_auth.db") as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
            conn.commit()

        listed = client.get(
            "/api/v1/admin/workspaces",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert listed.status_code == 200, listed.text
        workspace = next(
            item for item in listed.json()["workspaces"] if item["owner"]["email"] == email
        )
        workspace_id = workspace["id"]

        detail = client.get(
            f"/api/v1/admin/workspaces/{workspace_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["owner"]["email"] == email
        assert detail.json()["credit_balance"] == detail.json()["owner"]["credits"]
        starting_credits = detail.json()["owner"]["credits"]
        idempotency_key = str(uuid.uuid4())

        credits = client.post(
            f"/api/v1/admin/workspaces/{workspace_id}/credits",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 25, "note": "manual correction", "idempotency_key": idempotency_key},
        )
        assert credits.status_code == 200, credits.text
        assert credits.json()["balance_after"] == starting_credits + 25

        replayed_credits = client.post(
            f"/api/v1/admin/workspaces/{workspace_id}/credits",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"amount": 25, "note": "manual correction", "idempotency_key": idempotency_key},
        )
        assert replayed_credits.status_code == 200, replayed_credits.text
        assert replayed_credits.json()["balance_after"] == starting_credits + 25

        plan = client.put(
            f"/api/v1/admin/workspaces/{workspace_id}/plan",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"plan": "pro", "reason": "support upgrade"},
        )
        assert plan.status_code == 200, plan.text
        assert plan.json()["old_plan"] == "free"
        assert plan.json()["new_plan"] == "pro"

        updated_detail = client.get(
            f"/api/v1/admin/workspaces/{workspace_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert updated_detail.status_code == 200, updated_detail.text
        assert updated_detail.json()["owner"]["credits"] == starting_credits + 25
        assert updated_detail.json()["credit_balance"] == starting_credits + 25
        assert updated_detail.json()["active_plan_key"] == "pro"

        with sqlite3.connect("test_auth.db") as conn:
            ledger_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM credit_ledger cl
                JOIN users u ON cl.user_id = u.id
                WHERE u.email = ? AND cl.idempotency_key = ?
                """,
                (email, idempotency_key),
            ).fetchone()[0]
            ledger_balance = conn.execute(
                """
                SELECT cl.balance_after
                FROM credit_ledger cl
                JOIN users u ON cl.user_id = u.id
                WHERE u.email = ?
                ORDER BY cl.created_at DESC
                LIMIT 1
                """,
                (email,),
            ).fetchone()[0]
            projected_balance = conn.execute(
                """
                SELECT cb.balance
                FROM credit_balances cb
                JOIN users u ON cb.workspace_id = u.id
                WHERE u.email = ?
                LIMIT 1
                """,
                (email,),
            ).fetchone()[0]

        assert ledger_count == 1
        assert ledger_balance == projected_balance == starting_credits + 25

        blocked = client.put(
            f"/api/v1/admin/workspaces/{workspace_id}/status",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"blocked": True, "reason": "fraud review"},
        )
        assert blocked.status_code == 200, blocked.text
        assert blocked.json()["workspace_status"] == "blocked"
        assert blocked.json()["owner_is_active"] is False
        denied_after_block = client.get(
            f"/api/v1/admin/workspaces/{workspace_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert denied_after_block.status_code == 401, denied_after_block.text


def test_admin_runtime_config_reload_only_updates_whitelisted_fields(monkeypatch):
    fake_redis = _FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(main_module, "_redis_pool", None)
    monkeypatch.setattr(main_module, "_get_redis", _fake_get_redis)
    email = f"{uuid.uuid4()}@example.com"

    previous_agents_raw = settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW
    previous_enabled = settings.PRIVATE_ORCHESTRATOR_ENABLED
    previous_jwt_secret = settings.JWT_SECRET_KEY

    try:
        with TestClient(app) as client:
            register = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "Password1", "full_name": "Runtime Reload"},
            )
            assert register.status_code == 201, register.text
            access_token = register.json()["access_token"]

            with sqlite3.connect("test_auth.db") as conn:
                conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
                conn.commit()

            monkeypatch.setenv("PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW", "operator,planner")
            monkeypatch.setenv("PRIVATE_ORCHESTRATOR_ENABLED", "true")
            monkeypatch.setenv(
                "JWT_SECRET_KEY",
                "different-secret-key-that-must-not-reload-at-runtime-123456",
            )

            dry_run = client.post(
                "/api/v1/admin/runtime-config/reload",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"dry_run": True},
            )
            assert dry_run.status_code == 200, dry_run.text
            assert "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW" in dry_run.json()["changed"]
            assert "JWT_SECRET_KEY" not in dry_run.json()["changed"]
            assert settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW == previous_agents_raw
            assert settings.JWT_SECRET_KEY == previous_jwt_secret

            reloaded = client.post(
                "/api/v1/admin/runtime-config/reload",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"dry_run": False},
            )
            assert reloaded.status_code == 200, reloaded.text
            assert reloaded.json()["changed"]["PRIVATE_ORCHESTRATOR_ENABLED"]["new"] is True
            assert settings.PRIVATE_ORCHESTRATOR_ENABLED is True
            assert settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS == ["operator", "planner"]
            assert settings.JWT_SECRET_KEY == previous_jwt_secret

            snapshot = client.get(
                "/api/v1/admin/runtime-config",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert snapshot.status_code == 200, snapshot.text
            assert snapshot.json()["PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS"] == ["operator", "planner"]
    finally:
        settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW = previous_agents_raw
        settings.PRIVATE_ORCHESTRATOR_ENABLED = previous_enabled
        settings.JWT_SECRET_KEY = previous_jwt_secret


def test_workspace_blocked_even_when_user_stays_active(monkeypatch):
    fake_redis = _FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(main_module, "_redis_pool", None)
    monkeypatch.setattr(main_module, "_get_redis", _fake_get_redis)
    email = f"{uuid.uuid4()}@example.com"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Workspace Guard"},
        )
        assert register.status_code == 201, register.text
        access_token = register.json()["access_token"]

        with sqlite3.connect("test_auth.db") as conn:
            conn.execute(
                """
                UPDATE workspaces
                SET status = 'blocked'
                WHERE owner_user_id = (SELECT id FROM users WHERE email = ?)
                """,
                (email,),
            )
            conn.execute("UPDATE users SET is_active = 1 WHERE email = ?", (email,))
            conn.commit()

        blocked = client.get(
            "/api/v1/billing/usage",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert blocked.status_code == 403, blocked.text
        assert blocked.json()["detail"] == "Workspace inactive"


def test_admin_metrics_expose_finops_summary(monkeypatch):
    fake_redis = _FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(main_module, "_redis_pool", None)
    monkeypatch.setattr(main_module, "_get_redis", _fake_get_redis)
    admin_email = f"{uuid.uuid4()}@example.com"
    churn_email = f"{uuid.uuid4()}@example.com"
    now = datetime.now(timezone.utc).isoformat()

    with TestClient(app) as client:
        admin_register = client.post(
            "/api/v1/auth/register",
            json={"email": admin_email, "password": "Password1", "full_name": "FinOps Admin"},
        )
        assert admin_register.status_code == 201, admin_register.text
        access_token = admin_register.json()["access_token"]

        churn_register = client.post(
            "/api/v1/auth/register",
            json={"email": churn_email, "password": "Password1", "full_name": "Churned Workspace"},
        )
        assert churn_register.status_code == 201, churn_register.text

        with sqlite3.connect("test_auth.db") as conn:
            admin_user_id, admin_workspace_id = conn.execute(
                """
                SELECT u.id, w.id
                FROM users u
                JOIN workspaces w ON w.owner_user_id = u.id
                WHERE u.email = ?
                """,
                (admin_email,),
            ).fetchone()
            churn_user_id, churn_workspace_id = conn.execute(
                """
                SELECT u.id, w.id
                FROM users u
                JOIN workspaces w ON w.owner_user_id = u.id
                WHERE u.email = ?
                """,
                (churn_email,),
            ).fetchone()

            conn.execute(
                "UPDATE users SET is_admin = 1, plan = 'pro' WHERE email = ?",
                (admin_email,),
            )
            conn.execute(
                "UPDATE users SET plan = 'business' WHERE email = ?",
                (churn_email,),
            )
            conn.execute(
                """
                INSERT INTO subscriptions (
                    id, user_id, stripe_subscription_id, billing_interval, plan, status,
                    current_period_start, current_period_end, cancel_at_period_end, trial_end,
                    seats_allocated, seats_used, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    admin_user_id,
                    f"sub_{uuid.uuid4().hex}",
                    "monthly",
                    "pro",
                    "active",
                    now,
                    now,
                    0,
                    None,
                    1,
                    1,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO subscriptions (
                    id, user_id, stripe_subscription_id, billing_interval, plan, status,
                    current_period_start, current_period_end, cancel_at_period_end, trial_end,
                    seats_allocated, seats_used, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    churn_user_id,
                    f"sub_{uuid.uuid4().hex}",
                    "monthly",
                    "business",
                    "canceled",
                    now,
                    now,
                    1,
                    None,
                    5,
                    1,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO invoices (
                    id, workspace_id, subscription_id, provider_invoice_id, invoice_number, status,
                    currency, subtotal_cents, total_cents, period_start, period_end, issued_at,
                    paid_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    admin_workspace_id,
                    None,
                    f"in_{uuid.uuid4().hex}",
                    "INV-001",
                    "paid",
                    "USD",
                    12000,
                    12000,
                    now,
                    now,
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO usage_events (
                    id, workspace_id, actor_user_id, request_id, idempotency_key, event_type,
                    quantity, cost_usd, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    admin_workspace_id,
                    admin_user_id,
                    f"req_{uuid.uuid4().hex}",
                    f"usage_{uuid.uuid4().hex}",
                    "ai_usage",
                    100,
                    145,
                    "{}",
                    now,
                ),
            )
            conn.commit()

        metrics = client.get(
            "/api/v1/admin/metrics",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert metrics.status_code == 200, metrics.text
        payload = metrics.json()
        assert payload["estimated_mrr_usd"] == 79.0
        assert payload["trailing_30d_revenue_usd"] == 120.0
        assert payload["trailing_30d_usage_cost_usd"] == 145.0
        assert payload["trailing_30d_gross_margin_usd"] == -25.0
        assert payload["churn_rate_30d"] == 1.0
        assert payload["ltv_estimate_usd"] == 79.0
        assert payload["cac_estimate_usd"] is None
        assert uuid.UUID(payload["top_unprofitable_workspaces"][0]["workspace_id"]).hex == admin_workspace_id
        assert payload["top_unprofitable_workspaces"][0]["trailing_30d_margin_usd"] == -25.0


def test_private_orchestrator_admin_routes_are_hidden_when_flag_is_off(monkeypatch):
    previous_flag = settings.PRIVATE_ORCHESTRATOR_ENABLED
    email = f"{uuid.uuid4()}@example.com"

    try:
        monkeypatch.setattr(settings, "PRIVATE_ORCHESTRATOR_ENABLED", False)

        with TestClient(app) as client:
            register = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "Password1", "full_name": "Private Slice Off"},
            )
            assert register.status_code == 201, register.text
            access_token = register.json()["access_token"]

            with sqlite3.connect("test_auth.db") as conn:
                conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
                conn.commit()

            response = client.get(
                "/api/v1/admin/orchestrator/overview",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert response.status_code == 404, response.text
    finally:
        settings.PRIVATE_ORCHESTRATOR_ENABLED = previous_flag


def test_private_orchestrator_admin_routes_return_safe_contract(monkeypatch):
    from api.services import private_orchestrator_service

    previous_flag = settings.PRIVATE_ORCHESTRATOR_ENABLED
    previous_agents = settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW
    email = f"{uuid.uuid4()}@example.com"

    async def _fake_health():
        return {
            "ok": True,
            "status": "ok",
            "service": "ai-orchestrator",
            "version": "1.0.0",
            "detail": None,
        }

    async def _fake_agents():
        return (
            [
                {
                    "key": "operator",
                    "name": "AI Personal Operator",
                    "description": "Assistant executif",
                    "allowed": True,
                },
                {
                    "key": "ghost_agency",
                    "name": "Ghost Automation Agency",
                    "description": "Prospection privee",
                    "allowed": True,
                },
            ],
            "upstream",
        )

    try:
        monkeypatch.setattr(settings, "PRIVATE_ORCHESTRATOR_ENABLED", True)
        monkeypatch.setattr(settings, "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW", "operator,ghost_agency")
        monkeypatch.setattr(private_orchestrator_service, "fetch_upstream_health", _fake_health)
        monkeypatch.setattr(private_orchestrator_service, "fetch_upstream_agents", _fake_agents)

        with TestClient(app) as client:
            register = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "Password1", "full_name": "Private Slice On"},
            )
            assert register.status_code == 201, register.text
            access_token = register.json()["access_token"]

            forbidden = client.get(
                "/api/v1/admin/orchestrator/overview",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert forbidden.status_code == 403, forbidden.text

            with sqlite3.connect("test_auth.db") as conn:
                conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
                conn.commit()

            overview = client.get(
                "/api/v1/admin/orchestrator/overview",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert overview.status_code == 200, overview.text
            payload = overview.json()
            assert payload["enabled"] is True
            assert payload["access"]["admin_only"] is True
            assert payload["access"]["public_saas_exposure"] is False
            assert payload["access"]["destructive_merge_with_my_agent_hub"] is False
            assert payload["capabilities"]["planner_preview"] is True
            assert payload["capabilities"]["agent_routing"] is True
            assert payload["capabilities"]["prompt_execution"] is False
            assert payload["capabilities"]["terminal_access"] is False
            assert payload["allowed_agent_keys"] == ["operator", "ghost_agency"]

            agents = client.get(
                "/api/v1/admin/orchestrator/agents",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert agents.status_code == 200, agents.text
            agents_payload = agents.json()
            assert agents_payload["enabled"] is True
            assert agents_payload["source"] == "upstream"
            assert [item["key"] for item in agents_payload["agents"]] == ["operator", "ghost_agency"]
    finally:
        settings.PRIVATE_ORCHESTRATOR_ENABLED = previous_flag
        settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW = previous_agents


def test_private_orchestrator_preview_returns_scored_route(monkeypatch):
    from api.services import private_orchestrator_service

    previous_flag = settings.PRIVATE_ORCHESTRATOR_ENABLED
    previous_agents = settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW
    email = f"{uuid.uuid4()}@example.com"

    async def _fake_health():
        return {
            "ok": True,
            "status": "ok",
            "service": "ai-orchestrator",
            "version": "1.0.0",
            "detail": None,
        }

    try:
        monkeypatch.setattr(settings, "PRIVATE_ORCHESTRATOR_ENABLED", True)
        monkeypatch.setattr(settings, "PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW", "operator,ghost_agency,decision_engine")
        monkeypatch.setattr(private_orchestrator_service, "fetch_upstream_health", _fake_health)

        with TestClient(app) as client:
            register = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "Password1", "full_name": "Preview Admin"},
            )
            assert register.status_code == 201, register.text
            access_token = register.json()["access_token"]

            with sqlite3.connect("test_auth.db") as conn:
                conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
                conn.commit()

            preview = client.post(
                "/api/v1/admin/orchestrator/preview",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"message": "Compare scenarios and recommend the best strategy."},
            )
            assert preview.status_code == 200, preview.text
            payload = preview.json()
            assert payload["selected_agent_key"] == "decision_engine"
            assert payload["intent"] == "decision-support"
            assert payload["memory"]["message_count"] == 0
            assert payload["candidates"][0]["score"] >= payload["candidates"][1]["score"]
    finally:
        settings.PRIVATE_ORCHESTRATOR_ENABLED = previous_flag
        settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS_RAW = previous_agents


def test_admin_webhook_reprocess_recovers_failed_event(monkeypatch):
    from api.routers import admin as admin_module

    email = f"{uuid.uuid4()}@example.com"
    event_id = f"evt_{uuid.uuid4().hex}"
    process_event = AsyncMock(return_value="processed")
    monkeypatch.setattr(admin_module, "process_stripe_event", process_event)
    monkeypatch.setattr(
        admin_module.stripe.Event,
        "retrieve",
        lambda requested_id: {
            "id": requested_id,
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_replay"}},
        },
    )

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Webhook Admin"},
        )
        assert register.status_code == 201, register.text
        access_token = register.json()["access_token"]

        with sqlite3.connect("test_auth.db") as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
            conn.execute(
                """
                INSERT INTO webhook_events (id, stripe_event_id, event_type, processed_at, status, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    event_id,
                    "customer.subscription.updated",
                    datetime.now(timezone.utc).isoformat(),
                    "failed",
                    "prior failure",
                ),
            )
            conn.commit()

        response = client.post(
            f"/api/v1/admin/webhooks/{event_id}/reprocess",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "processed"
        assert response.json()["forced"] is False
        process_event.assert_awaited_once()

        with sqlite3.connect("test_auth.db") as conn:
            row = conn.execute(
                "SELECT status, error FROM webhook_events WHERE stripe_event_id = ?",
                (event_id,),
            ).fetchone()

        assert row == ("processed", None)


def test_admin_webhook_reprocess_requires_force_for_processed_event():
    email = f"{uuid.uuid4()}@example.com"
    event_id = f"evt_{uuid.uuid4().hex}"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Replay Guard"},
        )
        assert register.status_code == 201, register.text
        access_token = register.json()["access_token"]

        with sqlite3.connect("test_auth.db") as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
            conn.execute(
                """
                INSERT INTO webhook_events (id, stripe_event_id, event_type, processed_at, status, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    event_id,
                    "invoice.payment_succeeded",
                    datetime.now(timezone.utc).isoformat(),
                    "processed",
                    None,
                ),
            )
            conn.commit()

        response = client.post(
            f"/api/v1/admin/webhooks/{event_id}/reprocess",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 409, response.text
        assert "force=true" in response.json()["detail"]


def test_admin_webhook_reprocess_force_replays_processed_event(monkeypatch):
    from api.routers import admin as admin_module

    email = f"{uuid.uuid4()}@example.com"
    event_id = f"evt_{uuid.uuid4().hex}"
    process_event = AsyncMock(return_value="processed")
    monkeypatch.setattr(admin_module, "process_stripe_event", process_event)
    monkeypatch.setattr(
        admin_module.stripe.Event,
        "retrieve",
        lambda requested_id: {
            "id": requested_id,
            "type": "invoice.payment_succeeded",
            "data": {"object": {"id": "in_force_replay"}},
        },
    )

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Replay Force"},
        )
        assert register.status_code == 201, register.text
        access_token = register.json()["access_token"]

        with sqlite3.connect("test_auth.db") as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
            conn.execute(
                """
                INSERT INTO webhook_events (id, stripe_event_id, event_type, processed_at, status, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    event_id,
                    "invoice.payment_succeeded",
                    datetime.now(timezone.utc).isoformat(),
                    "processed",
                    None,
                ),
            )
            conn.commit()

        response = client.post(
            f"/api/v1/admin/webhooks/{event_id}/reprocess",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"force": True},
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "processed"
        assert response.json()["forced"] is True
        process_event.assert_awaited_once()


def test_admin_webhook_reprocess_persists_failure_state(monkeypatch):
    from api.routers import admin as admin_module

    email = f"{uuid.uuid4()}@example.com"
    event_id = f"evt_{uuid.uuid4().hex}"
    process_event = AsyncMock(side_effect=RuntimeError("processor exploded"))
    monkeypatch.setattr(admin_module, "process_stripe_event", process_event)
    monkeypatch.setattr(
        admin_module.stripe.Event,
        "retrieve",
        lambda requested_id: {
            "id": requested_id,
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_failure"}},
        },
    )

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Replay Failure"},
        )
        assert register.status_code == 201, register.text
        access_token = register.json()["access_token"]

        with sqlite3.connect("test_auth.db") as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
            conn.execute(
                """
                INSERT INTO webhook_events (id, stripe_event_id, event_type, processed_at, status, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    event_id,
                    "customer.subscription.updated",
                    datetime.now(timezone.utc).isoformat(),
                    "failed",
                    "prior failure",
                ),
            )
            conn.commit()

        response = client.post(
            f"/api/v1/admin/webhooks/{event_id}/reprocess",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 502, response.text
        assert "processor exploded" in response.json()["detail"]
        process_event.assert_awaited_once()

        with sqlite3.connect("test_auth.db") as conn:
            row = conn.execute(
                "SELECT status, error FROM webhook_events WHERE stripe_event_id = ?",
                (event_id,),
            ).fetchone()

        assert row == ("failed", "processor exploded")
