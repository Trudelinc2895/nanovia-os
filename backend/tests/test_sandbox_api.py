from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.config import settings
from api.routers.sandbox import router as sandbox_router
from api.services import sandbox_service


REPO_ROOT = Path(__file__).resolve().parents[2]


def _configure_sandbox_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog_path = tmp_path / "shared" / "catalog" / "monetization.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "shared" / "catalog" / "monetization.json", catalog_path)

    workspaces_path = tmp_path / "data" / "sandbox" / "workspaces.json"
    workspaces_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "data" / "sandbox" / "workspaces.json", workspaces_path)

    runtime_path = tmp_path / "data" / "sandbox" / "runtime-state.json"
    runtime_path.write_text(
        json.dumps(
            {
                "module_toggles": {},
                "bot_toggles": {},
                "processed_webhook_ids": [],
                "checkouts": [],
                "portal_sessions": [],
                "bot_runs": [],
            }
        ),
        encoding="utf-8",
    )

    credit_path = tmp_path / "data" / "sandbox" / "credit-ledger.json"
    shutil.copy(REPO_ROOT / "data" / "sandbox" / "credit-ledger.json", credit_path)

    usage_path = tmp_path / "data" / "sandbox" / "usage-events.json"
    shutil.copy(REPO_ROOT / "data" / "sandbox" / "usage-events.json", usage_path)

    audit_path = tmp_path / "data" / "audit" / "sandbox-audit.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text("", encoding="utf-8")

    memory_path = tmp_path / "data" / "memory" / "sandbox-memory.json"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("[]", encoding="utf-8")

    summaries_path = tmp_path / "data" / "memory" / "summaries.json"
    summaries_path.write_text("[]", encoding="utf-8")

    profile_path = tmp_path / "data" / "memory" / "user-profile.json"
    profile_path.write_text(json.dumps({"profiles": []}), encoding="utf-8")

    monkeypatch.setattr(sandbox_service, "CATALOG_PATH", catalog_path)
    monkeypatch.setattr(sandbox_service, "WORKSPACES_PATH", workspaces_path)
    monkeypatch.setattr(sandbox_service, "RUNTIME_STATE_PATH", runtime_path)
    monkeypatch.setattr(sandbox_service, "CREDIT_LEDGER_PATH", credit_path)
    monkeypatch.setattr(sandbox_service, "USAGE_EVENTS_PATH", usage_path)
    monkeypatch.setattr(sandbox_service, "AUDIT_LOG_PATH", audit_path)
    monkeypatch.setattr(sandbox_service, "MEMORY_PATH", memory_path)
    monkeypatch.setattr(sandbox_service, "SUMMARIES_PATH", summaries_path)
    monkeypatch.setattr(sandbox_service, "PROFILE_PATH", profile_path)


@pytest.fixture()
def sandbox_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    _configure_sandbox_paths(tmp_path, monkeypatch)

    monkeypatch.setattr(settings, "APP_ENV", "sandbox")
    monkeypatch.setattr(settings, "STRIPE_MODE", "test")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test_sandbox")
    monkeypatch.setattr(settings, "STRIPE_PRICE_STARTER_MONTHLY_ID", "price_starter_monthly")
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO_MONTHLY_ID", "price_pro_monthly")
    monkeypatch.setattr(settings, "STRIPE_PRICE_BUSINESS_MONTHLY_ID", "price_business_monthly")
    monkeypatch.setattr(settings, "BOTS_ENABLED", True)
    monkeypatch.setattr(settings, "DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION", True)
    monkeypatch.setattr(settings, "AUDIT_LOG_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_TARGET_GROSS_MARGIN_PCT", 70)

    app = FastAPI()
    app.include_router(sandbox_router)
    return TestClient(app)


def _stripe_signature(payload: dict[str, object], secret: str = "whsec_test_sandbox") -> tuple[str, bytes]:
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}", body


def test_plans_modules_and_status_are_available(sandbox_client: TestClient):
    plans = sandbox_client.get("/billing/plans")
    assert plans.status_code == 200
    plan_ids = [plan["id"] for plan in plans.json()]
    assert plan_ids == ["starter", "pro", "business"]

    modules = sandbox_client.get("/modules")
    assert modules.status_code == 200
    module_map = {module["id"]: module for module in modules.json()}
    assert module_map["billing_monetization"]["billing_metered"] is True
    assert module_map["integration_hub"]["required_plan"] == "business"

    status_response = sandbox_client.get("/sandbox/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["stripe_catalog_ready"]["starter"] is True
    assert status_payload["profitability"]["monthly_revenue_usd"] >= 257


def test_entitlements_usage_and_credit_ledger_flow(sandbox_client: TestClient):
    entitlements = sandbox_client.get("/billing/entitlements", params={"workspace_id": "sandbox_pro"})
    assert entitlements.status_code == 200
    payload = entitlements.json()
    assert payload["plan"] == "pro"
    assert payload["modules"]["ai_orchestrator"] is True
    assert payload["modules"]["security_center"] is False

    usage_record = sandbox_client.post(
        "/usage/record",
        json={
            "workspace_id": "sandbox_pro",
            "actor": "billing_agent",
            "kind": "ai_request",
            "model": "gpt-4.1-mini",
            "units": 12,
            "input_tokens": 6000,
            "output_tokens": 1500,
            "reason": "sandbox prompt test",
        },
    )
    assert usage_record.status_code == 200
    credits_after_usage = usage_record.json()["credits"]
    assert credits_after_usage["used"] >= 252

    adjustment = sandbox_client.post(
        "/admin/workspaces/sandbox_pro/credits/adjust",
        json={"amount": 75, "actor": "admin", "reason": "Manual profitability buffer"},
    )
    assert adjustment.status_code == 200
    assert adjustment.json()["credits"]["adjustments"] >= 225

    credits = sandbox_client.get("/credits", params={"workspace_id": "sandbox_pro"})
    assert credits.status_code == 200
    assert len(credits.json()["ledger"]) >= 2


def test_checkout_portal_and_subscription_flow(sandbox_client: TestClient):
    checkout = sandbox_client.post(
        "/billing/checkout",
        json={"workspace_id": "sandbox_workspace", "plan": "starter", "actor": "admin"},
    )
    assert checkout.status_code == 200
    checkout_payload = checkout.json()
    assert checkout_payload["price_id"] == "price_starter_monthly"

    subscription = sandbox_client.get("/billing/subscription", params={"workspace_id": "sandbox_workspace"})
    assert subscription.status_code == 200
    assert subscription.json()["checkout_session_id"] == checkout_payload["id"]

    portal = sandbox_client.post(
        "/billing/portal",
        json={"workspace_id": "sandbox_workspace", "return_url": "http://localhost:3020/portal", "actor": "admin"},
    )
    assert portal.status_code == 200
    assert portal.json()["provider"] == "sandbox"


def test_webhook_idempotency_and_workspace_blocking(sandbox_client: TestClient):
    event = {
        "id": "evt_checkout_complete",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_evt",
                "customer": "cus_test",
                "subscription": "sub_test",
                "client_reference_id": "sandbox_workspace",
                "metadata": {"workspace_id": "sandbox_workspace", "plan": "starter"},
            }
        },
    }
    signature, body = _stripe_signature(event)

    first = sandbox_client.post("/stripe/webhook", data=body, headers={"Stripe-Signature": signature})
    assert first.status_code == 200
    assert first.json()["applied"] is True

    second = sandbox_client.post("/stripe/webhook", data=body, headers={"Stripe-Signature": signature})
    assert second.status_code == 200
    assert second.json()["status"] == "idempotent"

    blocked = sandbox_client.post(
        "/admin/workspaces/sandbox_workspace/block",
        json={"actor": "admin", "reason": "Sandbox billing delinquent"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["blocked"] is True

    blocked_usage = sandbox_client.post(
        "/usage/record",
        json={"workspace_id": "sandbox_workspace", "actor": "system", "units": 1},
    )
    assert blocked_usage.status_code == 403


def test_agents_bots_module_toggle_and_memory_guard(sandbox_client: TestClient):
    agents = sandbox_client.get("/agents")
    assert agents.status_code == 200
    agent_ids = {agent["id"] for agent in agents.json()}
    assert {"orchestrator", "billing_agent", "module_agent"}.issubset(agent_ids)

    blocked_dangerous = sandbox_client.post(
        "/agents/route",
        json={"task": "Delete production firewall rule", "workspace_id": "sandbox_business", "actor": "admin"},
    )
    assert blocked_dangerous.status_code == 409

    allowed_dangerous = sandbox_client.post(
        "/agents/route",
        json={
            "task": "Delete sandbox docker volume",
            "workspace_id": "sandbox_business",
            "actor": "admin",
            "confirm_dangerous_action": True,
        },
    )
    assert allowed_dangerous.status_code == 200
    assert allowed_dangerous.json()["routed_by"] == "orchestrator"
    assert allowed_dangerous.json()["selected_agent"] == "devops_agent"

    toggle = sandbox_client.post(
        "/admin/modules/notification_center/toggle-sandbox",
        json={"enabled": False, "actor": "admin", "reason": "Testing disabled notifications"},
    )
    assert toggle.status_code == 200
    assert toggle.json()["sandbox_enabled"] is False

    bots = sandbox_client.get("/bots")
    assert bots.status_code == 200
    bot_ids = {bot["id"] for bot in bots.json()}
    assert {"stripe_test_bot", "module_test_bot"}.issubset(bot_ids)

    run_bot = sandbox_client.post(
        "/bots/module_test_bot/run",
        json={"workspace_id": "sandbox_business", "actor": "automation_bot"},
    )
    assert run_bot.status_code == 200
    assert run_bot.json()["result"]["routed_by"] == "orchestrator"

    memory_ok = sandbox_client.post("/memory/save", json={"content": "Workspace sandbox_pro likes concise summaries."})
    assert memory_ok.status_code == 200

    memory_blocked = sandbox_client.post("/memory/save", json={"content": "Secret sk_test_123 should not be stored."})
    assert memory_blocked.status_code == 400
