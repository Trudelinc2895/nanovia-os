from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from api.config import settings

ROOT_DIR = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT_DIR / "shared" / "catalog" / "monetization.json"
WORKSPACES_PATH = ROOT_DIR / "data" / "sandbox" / "workspaces.json"
RUNTIME_STATE_PATH = ROOT_DIR / "data" / "sandbox" / "runtime-state.json"
CREDIT_LEDGER_PATH = ROOT_DIR / "data" / "sandbox" / "credit-ledger.json"
USAGE_EVENTS_PATH = ROOT_DIR / "data" / "sandbox" / "usage-events.json"
AUDIT_LOG_PATH = ROOT_DIR / "data" / "audit" / "sandbox-audit.jsonl"
MEMORY_PATH = ROOT_DIR / "data" / "memory" / "sandbox-memory.json"
SUMMARIES_PATH = ROOT_DIR / "data" / "memory" / "summaries.json"
PROFILE_PATH = ROOT_DIR / "data" / "memory" / "user-profile.json"

OPENAI_RATE_CARD = {
    "gpt-4.1-mini": {"input_per_1k": 0.0004, "output_per_1k": 0.0016},
    "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
    "gpt-4.1": {"input_per_1k": 0.0020, "output_per_1k": 0.0080},
}

DANGEROUS_ACTION_KEYWORDS = (
    "delete",
    "drop",
    "destroy",
    "wipe",
    "shutdown",
    "firewall",
    "dns live",
    "production",
)
SAFE_MODULES_WHEN_DELINQUENT = {"core_platform", "billing_monetization", "support_crm"}
STRIPE_PRICE_ENV_BY_PLAN = {
    "starter": "STRIPE_PRICE_STARTER_MONTHLY_ID",
    "pro": "STRIPE_PRICE_PRO_MONTHLY_ID",
    "business": "STRIPE_PRICE_BUSINESS_MONTHLY_ID",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _billing_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path, [])
    if isinstance(data, list):
        return data
    return []


def _read_json_object(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    data = _read_json(path, default)
    if isinstance(data, dict):
        return data
    return default.copy()


def load_official_sandbox_catalog() -> dict[str, Any]:
    catalog = _read_json(CATALOG_PATH, {})
    official = catalog.get("official_sandbox")
    if not isinstance(official, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Official sandbox catalog is missing.",
        )
    return official


def _catalog_modules_by_id() -> dict[str, dict[str, Any]]:
    modules = load_official_sandbox_catalog().get("modules", [])
    return {
        module["id"]: module
        for module in modules
        if isinstance(module, dict) and isinstance(module.get("id"), str)
    }


def _catalog_plans_by_id() -> dict[str, dict[str, Any]]:
    plans = load_official_sandbox_catalog().get("plans", [])
    return {
        plan["id"]: plan
        for plan in plans
        if isinstance(plan, dict) and isinstance(plan.get("id"), str)
    }


def _catalog_agents_by_id() -> dict[str, dict[str, Any]]:
    agents = load_official_sandbox_catalog().get("agents", [])
    return {
        agent["id"]: agent
        for agent in agents
        if isinstance(agent, dict) and isinstance(agent.get("id"), str)
    }


def _catalog_bots_by_id() -> dict[str, dict[str, Any]]:
    bots = load_official_sandbox_catalog().get("bots", [])
    return {
        bot["id"]: bot
        for bot in bots
        if isinstance(bot, dict) and isinstance(bot.get("id"), str)
    }


def _default_workspace(workspace_id: str = "sandbox_workspace", plan: str = "starter") -> dict[str, Any]:
    return {
        "id": workspace_id,
        "name": workspace_id.replace("_", " ").title(),
        "plan": plan,
        "override_plan": None,
        "subscription_status": "active",
        "blocked": False,
        "blocked_reason": None,
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "stripe_checkout_session_id": None,
        "usage_summary": {
            "period": _billing_period(),
            "credits_used": 0,
            "estimated_openai_cost_usd": 0.0,
        },
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
    }


def _normalize_workspace(workspace: dict[str, Any]) -> dict[str, Any]:
    merged = _default_workspace(
        workspace_id=workspace.get("id") or "sandbox_workspace",
        plan=workspace.get("plan") or "starter",
    )
    merged.update(workspace)
    usage_summary = merged.get("usage_summary") or {}
    merged["usage_summary"] = {
        "period": usage_summary.get("period") or _billing_period(),
        "credits_used": int(usage_summary.get("credits_used", 0)),
        "estimated_openai_cost_usd": round(float(usage_summary.get("estimated_openai_cost_usd", 0.0)), 6),
    }
    merged["blocked"] = bool(merged.get("blocked", False))
    merged["updated_at"] = merged.get("updated_at") or _utcnow()
    return merged


def _load_workspace_store() -> dict[str, Any]:
    default_store = {
        "workspaces": [
            _default_workspace("sandbox_workspace", "starter"),
            _default_workspace("sandbox_pro", "pro"),
            _default_workspace("sandbox_business", "business"),
        ]
    }
    store = _read_json_object(WORKSPACES_PATH, default_store)
    workspaces = store.get("workspaces")
    if not isinstance(workspaces, list):
        workspaces = default_store["workspaces"]
    store["workspaces"] = [_normalize_workspace(item) for item in workspaces if isinstance(item, dict)]
    if not store["workspaces"]:
        store["workspaces"] = default_store["workspaces"]
    return store


def _save_workspace_store(store: dict[str, Any]) -> None:
    normalized = {"workspaces": [_normalize_workspace(item) for item in store.get("workspaces", [])]}
    _write_json(WORKSPACES_PATH, normalized)


def _load_runtime_state() -> dict[str, Any]:
    default_state = {
        "module_toggles": {},
        "bot_toggles": {},
        "processed_webhook_ids": [],
        "checkouts": [],
        "portal_sessions": [],
        "bot_runs": [],
    }
    state = _read_json_object(RUNTIME_STATE_PATH, default_state)
    for key, value in default_state.items():
        if key not in state or not isinstance(state[key], type(value)):
            state[key] = value
    return state


def _save_runtime_state(state: dict[str, Any]) -> None:
    _write_json(RUNTIME_STATE_PATH, state)


def _ledger_entries() -> list[dict[str, Any]]:
    return _read_json_list(CREDIT_LEDGER_PATH)


def _usage_events() -> list[dict[str, Any]]:
    return _read_json_list(USAGE_EVENTS_PATH)


def _memory_records() -> list[dict[str, Any]]:
    return _read_json_list(MEMORY_PATH)


def _memory_summaries() -> list[dict[str, Any]]:
    return _read_json_list(SUMMARIES_PATH)


def _profile_data() -> dict[str, Any]:
    return _read_json_object(PROFILE_PATH, {"profiles": []})


def _append_json_list(path: Path, entry: dict[str, Any]) -> None:
    data = _read_json_list(path)
    data.append(entry)
    _write_json(path, data)


def _secret_like(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ("sk_live", "sk_test_", "pk_live", "pk_test_", "whsec_", "api_key"))


def append_audit_entry(
    actor: str,
    agent: str,
    action: str,
    target: str,
    status_value: str,
    risk_level: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {
        "timestamp": _utcnow(),
        "environment": "sandbox",
        "sandbox": True,
        "actor": actor,
        "agent": agent,
        "action": action,
        "target": target,
        "status": status_value,
        "risk_level": risk_level,
        "details": details or {},
    }
    if settings.AUDIT_LOG_ENABLED:
        _ensure_parent(AUDIT_LOG_PATH)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return entry


def read_audit_entries(limit: int = 25) -> list[dict[str, Any]]:
    if not AUDIT_LOG_PATH.exists():
        return []
    lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-limit:] if line.strip()]


def list_plans() -> list[dict[str, Any]]:
    plans = load_official_sandbox_catalog().get("plans", [])
    if not isinstance(plans, list):
        return []
    return plans


def get_plan(plan_id: str) -> dict[str, Any]:
    plan = _catalog_plans_by_id().get(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown plan: {plan_id}")
    return plan


def list_modules() -> list[dict[str, Any]]:
    modules = load_official_sandbox_catalog().get("modules", [])
    state = _load_runtime_state()
    toggles = state.get("module_toggles", {})
    results: list[dict[str, Any]] = []
    for module in modules:
        if not isinstance(module, dict):
            continue
        merged = dict(module)
        if module.get("id") in toggles:
            merged["sandbox_enabled"] = bool(toggles[module["id"]])
            merged["enabled"] = bool(toggles[module["id"]])
        else:
            merged["sandbox_enabled"] = bool(module.get("sandbox_enabled", module.get("enabled", True)))
        results.append(merged)
    return results


def get_module(module_id: str) -> dict[str, Any]:
    modules = {module["id"]: module for module in list_modules() if isinstance(module.get("id"), str)}
    module = modules.get(module_id)
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown module: {module_id}")
    return module


def list_agents() -> list[dict[str, Any]]:
    agents = load_official_sandbox_catalog().get("agents", [])
    return [agent for agent in agents if isinstance(agent, dict)]


def list_bots() -> list[dict[str, Any]]:
    bots = load_official_sandbox_catalog().get("bots", [])
    state = _load_runtime_state()
    toggles = state.get("bot_toggles", {})
    results: list[dict[str, Any]] = []
    for bot in bots:
        if not isinstance(bot, dict):
            continue
        merged = dict(bot)
        if bot.get("id") in toggles:
            merged["enabled"] = bool(toggles[bot["id"]])
        results.append(merged)
    return results


def list_workspaces() -> list[dict[str, Any]]:
    store = _load_workspace_store()
    return store["workspaces"]


def get_workspace(workspace_id: str) -> dict[str, Any]:
    for workspace in list_workspaces():
        if workspace["id"] == workspace_id:
            return workspace
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown workspace: {workspace_id}")


def _save_workspace(updated_workspace: dict[str, Any]) -> dict[str, Any]:
    store = _load_workspace_store()
    workspaces = store["workspaces"]
    for index, workspace in enumerate(workspaces):
        if workspace["id"] == updated_workspace["id"]:
            updated_workspace["updated_at"] = _utcnow()
            workspaces[index] = _normalize_workspace(updated_workspace)
            _save_workspace_store(store)
            return workspaces[index]
    updated_workspace["updated_at"] = _utcnow()
    workspaces.append(_normalize_workspace(updated_workspace))
    _save_workspace_store(store)
    return updated_workspace


def _effective_plan_id(workspace: dict[str, Any]) -> str:
    return str(workspace.get("override_plan") or workspace.get("plan") or "starter")


def _effective_subscription_status(workspace: dict[str, Any]) -> str:
    if workspace.get("blocked"):
        return "blocked"
    return str(workspace.get("subscription_status") or "inactive")


def _workspace_ledger_summary(workspace_id: str) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    plan = get_plan(_effective_plan_id(workspace))
    monthly_limit = int(plan.get("monthly_credits", 0))
    period = _billing_period()

    ledger = [entry for entry in _ledger_entries() if entry.get("workspace_id") == workspace_id]
    usage = [
        entry
        for entry in _usage_events()
        if entry.get("workspace_id") == workspace_id and entry.get("period") == period
    ]

    adjustment_total = sum(int(entry.get("amount", 0)) for entry in ledger)
    used = sum(int(entry.get("credits_used", 0)) for entry in usage)
    estimated_openai_cost = round(sum(float(entry.get("estimated_openai_cost_usd", 0.0)) for entry in usage), 6)
    remaining = max(monthly_limit + adjustment_total - used, 0)

    return {
        "workspace_id": workspace_id,
        "period": period,
        "monthly_limit": monthly_limit,
        "adjustments": adjustment_total,
        "used": used,
        "remaining": remaining,
        "estimated_openai_cost_usd": estimated_openai_cost,
        "ledger_entries": len(ledger),
        "usage_events": len(usage),
    }


def get_credits(workspace_id: str = "sandbox_workspace") -> dict[str, Any]:
    summary = _workspace_ledger_summary(workspace_id)
    ledger = [entry for entry in _ledger_entries() if entry.get("workspace_id") == workspace_id]
    return {
        **summary,
        "ledger": ledger[-25:],
    }


def _estimate_openai_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = OPENAI_RATE_CARD.get(model, OPENAI_RATE_CARD.get(getattr(settings, "AI_MODEL", "gpt-4.1-mini"), OPENAI_RATE_CARD["gpt-4.1-mini"]))
    input_cost = (max(input_tokens, 0) / 1000) * rate["input_per_1k"]
    output_cost = (max(output_tokens, 0) / 1000) * rate["output_per_1k"]
    return round(input_cost + output_cost, 6)


def get_usage(workspace_id: str = "sandbox_workspace") -> dict[str, Any]:
    summary = _workspace_ledger_summary(workspace_id)
    period = summary["period"]
    events = [
        entry
        for entry in _usage_events()
        if entry.get("workspace_id") == workspace_id and entry.get("period") == period
    ]
    return {
        "workspace_id": workspace_id,
        "period": period,
        "credits_used": summary["used"],
        "estimated_openai_cost_usd": summary["estimated_openai_cost_usd"],
        "events": events[-50:],
    }


def record_usage(
    workspace_id: str,
    actor: str,
    kind: str,
    model: str,
    units: int,
    input_tokens: int,
    output_tokens: int,
    reason: str | None = None,
    credits_override: int | None = None,
) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    if workspace.get("blocked"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace is blocked.")

    tokens_total = max(input_tokens, 0) + max(output_tokens, 0)
    estimated_cost = _estimate_openai_cost(model, input_tokens, output_tokens)
    credits_used = credits_override if credits_override is not None else max(units, math.ceil(tokens_total / 1000) or 1)

    summary_before = _workspace_ledger_summary(workspace_id)
    if credits_used > summary_before["remaining"]:
        append_audit_entry(
            actor=actor,
            agent="billing_agent",
            action="record_usage",
            target=workspace_id,
            status_value="blocked",
            risk_level="medium",
            details={"reason": "usage_limit_exceeded", "credits_requested": credits_used},
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Usage limit exceeded for sandbox workspace.")

    event = {
        "id": f"usage_{uuid4().hex[:12]}",
        "workspace_id": workspace_id,
        "period": _billing_period(),
        "kind": kind,
        "model": model,
        "units": units,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "credits_used": credits_used,
        "estimated_openai_cost_usd": estimated_cost,
        "reason": reason or "sandbox usage",
        "actor": actor,
        "created_at": _utcnow(),
    }
    _append_json_list(USAGE_EVENTS_PATH, event)

    workspace["usage_summary"] = {
        "period": _billing_period(),
        "credits_used": summary_before["used"] + credits_used,
        "estimated_openai_cost_usd": round(summary_before["estimated_openai_cost_usd"] + estimated_cost, 6),
    }
    _save_workspace(workspace)
    summary_after = _workspace_ledger_summary(workspace_id)

    append_audit_entry(
        actor=actor,
        agent="billing_agent",
        action="record_usage",
        target=workspace_id,
        status_value="success",
        risk_level="low",
        details={"credits_used": credits_used, "estimated_openai_cost_usd": estimated_cost, "model": model},
    )

    return {
        "event": event,
        "credits": summary_after,
    }


def adjust_workspace_credits(workspace_id: str, amount: int, actor: str, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Reason is required.")
    get_workspace(workspace_id)
    entry = {
        "id": f"ledger_{uuid4().hex[:12]}",
        "workspace_id": workspace_id,
        "amount": int(amount),
        "reason": reason.strip(),
        "actor": actor,
        "created_at": _utcnow(),
        "type": "manual_admin_adjustment",
    }
    _append_json_list(CREDIT_LEDGER_PATH, entry)
    append_audit_entry(
        actor=actor,
        agent="billing_agent",
        action="adjust_credits",
        target=workspace_id,
        status_value="success",
        risk_level="medium",
        details={"amount": amount, "reason": reason},
    )
    return {
        "workspace_id": workspace_id,
        "adjustment": entry,
        "credits": _workspace_ledger_summary(workspace_id),
    }


def _plan_module_map(plan_id: str, subscription_status: str) -> dict[str, bool]:
    plan = get_plan(plan_id)
    plan_modules = set(plan.get("modules", []))
    toggled_modules = {module["id"]: module for module in list_modules()}
    module_state: dict[str, bool] = {}

    for module_id, module in toggled_modules.items():
        enabled_by_catalog = bool(module.get("sandbox_enabled", module.get("enabled", True)))
        enabled = enabled_by_catalog and module_id in plan_modules
        if subscription_status in {"past_due", "unpaid"}:
            enabled = enabled and module_id in SAFE_MODULES_WHEN_DELINQUENT
        if subscription_status in {"canceled", "blocked"}:
            enabled = module_id in {"billing_monetization", "support_crm"}
        module_state[module_id] = enabled
    return module_state


def get_entitlements(workspace_id: str = "sandbox_workspace") -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    plan_id = _effective_plan_id(workspace)
    plan = get_plan(plan_id)
    subscription_status = _effective_subscription_status(workspace)
    credits = _workspace_ledger_summary(workspace_id)
    modules = _plan_module_map(plan_id, subscription_status)
    monthly_revenue = float(plan.get("price_usd_monthly", 0))
    target_margin_pct = int(plan.get("target_gross_margin_pct", getattr(settings, "OPENAI_TARGET_GROSS_MARGIN_PCT", 70)))
    gross_margin = round(monthly_revenue - credits["estimated_openai_cost_usd"], 6)
    margin_pct = 0.0 if monthly_revenue <= 0 else round((gross_margin / monthly_revenue) * 100, 2)

    return {
        "workspace_id": workspace_id,
        "plan": plan_id,
        "subscription_status": subscription_status,
        "workspace_blocked": bool(workspace.get("blocked")),
        "modules": modules,
        "credits": {
            "monthly_limit": credits["monthly_limit"],
            "adjustments": credits["adjustments"],
            "used": credits["used"],
            "remaining": credits["remaining"],
        },
        "usage": {
            "estimated_openai_cost_usd": credits["estimated_openai_cost_usd"],
            "monthly_revenue_usd": monthly_revenue,
            "gross_margin_usd": gross_margin,
            "gross_margin_pct": margin_pct,
            "target_gross_margin_pct": target_margin_pct,
            "cost_guard_triggered": credits["estimated_openai_cost_usd"] > float(plan.get("openai_budget_usd", 0)),
        },
        "source_of_truth": "workspace + plan + subscription_status + credits + usage + admin_overrides",
    }


def get_subscription(workspace_id: str = "sandbox_workspace") -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    plan_id = _effective_plan_id(workspace)
    return {
        "workspace_id": workspace_id,
        "plan": plan_id,
        "subscription_status": _effective_subscription_status(workspace),
        "stripe_customer_id": workspace.get("stripe_customer_id"),
        "stripe_subscription_id": workspace.get("stripe_subscription_id"),
        "checkout_session_id": workspace.get("stripe_checkout_session_id"),
        "price_id": getattr(settings, STRIPE_PRICE_ENV_BY_PLAN.get(plan_id, ""), ""),
    }


def _require_active_workspace(workspace: dict[str, Any]) -> None:
    if workspace.get("blocked"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace is blocked.")


def create_checkout_session(
    workspace_id: str,
    plan_id: str,
    success_url: str | None,
    cancel_url: str | None,
    actor: str,
) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    _require_active_workspace(workspace)
    get_plan(plan_id)
    session_id = f"cs_sandbox_{uuid4().hex[:18]}"
    price_id = getattr(settings, STRIPE_PRICE_ENV_BY_PLAN.get(plan_id, ""), "")
    checkout = {
        "id": session_id,
        "workspace_id": workspace_id,
        "plan": plan_id,
        "price_id": price_id or None,
        "mode": "subscription",
        "provider": "sandbox",
        "status": "open",
        "success_url": success_url or "http://localhost:3000/sandbox/checkout/success",
        "cancel_url": cancel_url or "http://localhost:3000/sandbox/checkout/cancel",
        "created_at": _utcnow(),
    }
    state = _load_runtime_state()
    state["checkouts"].append(checkout)
    _save_runtime_state(state)

    workspace["stripe_checkout_session_id"] = session_id
    workspace["plan"] = plan_id
    _save_workspace(workspace)

    append_audit_entry(
        actor=actor,
        agent="billing_agent",
        action="create_checkout",
        target=workspace_id,
        status_value="success",
        risk_level="low",
        details={"plan": plan_id, "price_id": price_id},
    )
    return checkout


def create_portal_session(workspace_id: str, return_url: str | None, actor: str) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    _require_active_workspace(workspace)
    session = {
        "id": f"portal_sandbox_{uuid4().hex[:18]}",
        "workspace_id": workspace_id,
        "provider": "sandbox",
        "url": return_url or "http://localhost:3020/sandbox/portal",
        "created_at": _utcnow(),
    }
    state = _load_runtime_state()
    state["portal_sessions"].append(session)
    _save_runtime_state(state)
    append_audit_entry(
        actor=actor,
        agent="billing_agent",
        action="create_portal_session",
        target=workspace_id,
        status_value="success",
        risk_level="low",
        details={"return_url": session["url"]},
    )
    return session


def _extract_workspace_id_from_event(event: dict[str, Any]) -> str:
    data_object = event.get("data", {}).get("object", {})
    metadata = data_object.get("metadata", {}) if isinstance(data_object, dict) else {}
    for candidate in (
        metadata.get("workspace_id"),
        data_object.get("client_reference_id"),
        data_object.get("workspace_id"),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate
    return "sandbox_workspace"


def _verify_stripe_signature(payload: bytes, stripe_signature: str | None) -> None:
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not stripe_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe-Signature header.")
    if not secret or "replace_me" in secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sandbox webhook secret is not configured.")

    fragments = {}
    for item in stripe_signature.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        fragments[key.strip()] = value.strip()

    timestamp = fragments.get("t")
    signature = fragments.get("v1")
    if not timestamp or not signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature header.")

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stripe signature verification failed.")
    if abs(time.time() - int(timestamp)) > 300:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stripe signature timestamp is stale.")


def process_stripe_webhook(payload: bytes, stripe_signature: str | None) -> dict[str, Any]:
    _verify_stripe_signature(payload, stripe_signature)
    event = json.loads(payload.decode("utf-8"))
    event_id = event.get("id")
    if not event_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe event id is required.")

    state = _load_runtime_state()
    processed_ids = state.get("processed_webhook_ids", [])
    if event_id in processed_ids:
        append_audit_entry(
            actor="system",
            agent="billing_agent",
            action="process_webhook",
            target=event.get("type", "stripe_event"),
            status_value="success",
            risk_level="low",
            details={"event_id": event_id, "idempotent": True},
        )
        return {"event_id": event_id, "status": "idempotent", "applied": False}

    event_type = str(event.get("type", "unknown"))
    workspace_id = _extract_workspace_id_from_event(event)
    workspace = get_workspace(workspace_id)
    data_object = event.get("data", {}).get("object", {})
    metadata = data_object.get("metadata", {}) if isinstance(data_object, dict) else {}

    if event_type == "checkout.session.completed":
        workspace["subscription_status"] = "active"
        workspace["plan"] = metadata.get("plan") or workspace.get("plan") or "starter"
        workspace["stripe_customer_id"] = data_object.get("customer")
        workspace["stripe_checkout_session_id"] = data_object.get("id")
        workspace["stripe_subscription_id"] = data_object.get("subscription")
    elif event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        workspace["subscription_status"] = data_object.get("status", "active")
        workspace["stripe_subscription_id"] = data_object.get("id")
        workspace["stripe_customer_id"] = data_object.get("customer")
        workspace["plan"] = metadata.get("plan") or workspace.get("plan") or "starter"
    elif event_type == "customer.subscription.deleted":
        workspace["subscription_status"] = "canceled"
    elif event_type == "invoice.payment_succeeded":
        workspace["subscription_status"] = "active"
    elif event_type == "invoice.payment_failed":
        workspace["subscription_status"] = "past_due"
    elif event_type == "payment_method.attached":
        workspace["payment_method_attached"] = True
    elif event_type == "customer.updated":
        workspace["stripe_customer_id"] = data_object.get("id") or workspace.get("stripe_customer_id")
    elif event_type == "customer.subscription.trial_will_end":
        workspace["trial_warning"] = True

    _save_workspace(workspace)
    processed_ids.append(event_id)
    state["processed_webhook_ids"] = processed_ids[-500:]
    _save_runtime_state(state)

    append_audit_entry(
        actor="system",
        agent="billing_agent",
        action="process_webhook",
        target=event_type,
        status_value="success",
        risk_level="medium" if event_type == "invoice.payment_failed" else "low",
        details={"event_id": event_id, "workspace_id": workspace_id},
    )

    return {
        "event_id": event_id,
        "event_type": event_type,
        "workspace_id": workspace_id,
        "subscription": get_subscription(workspace_id),
        "entitlements": get_entitlements(workspace_id),
        "applied": True,
    }


def save_memory(content: str, actor: str = "memory_agent") -> dict[str, Any]:
    if _secret_like(content):
        append_audit_entry(
            actor=actor,
            agent="memory_agent",
            action="save_memory",
            target="sandbox_memory",
            status_value="blocked",
            risk_level="high",
            details={"reason": "secret_like_content"},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Secret-like content is not allowed in sandbox memory.")

    entry = {
        "id": f"memory_{uuid4().hex[:12]}",
        "content": content,
        "actor": actor,
        "created_at": _utcnow(),
    }
    _append_json_list(MEMORY_PATH, entry)
    _append_json_list(
        SUMMARIES_PATH,
        {"id": entry["id"], "summary": content[:120], "created_at": entry["created_at"], "actor": actor},
    )
    append_audit_entry(
        actor=actor,
        agent="memory_agent",
        action="save_memory",
        target="sandbox_memory",
        status_value="success",
        risk_level="low",
        details={"memory_id": entry["id"]},
    )
    return entry


def list_memory(limit: int = 25) -> dict[str, Any]:
    records = _memory_records()
    return {
        "items": records[-limit:],
        "summaries": _memory_summaries()[-limit:],
        "profiles": _profile_data().get("profiles", []),
    }


def search_memory(query: str) -> list[dict[str, Any]]:
    lowered = query.lower()
    return [entry for entry in _memory_records() if lowered in entry.get("content", "").lower()]


def override_workspace_plan(workspace_id: str, plan: str, actor: str = "admin", reason: str | None = None) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    get_plan(plan)
    workspace["override_plan"] = plan
    saved = _save_workspace(workspace)
    append_audit_entry(
        actor=actor,
        agent="billing_agent",
        action="override_plan",
        target=workspace_id,
        status_value="success",
        risk_level="medium",
        details={"plan": plan, "reason": reason},
    )
    return saved


def block_workspace(workspace_id: str, actor: str, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Reason is required.")
    workspace = get_workspace(workspace_id)
    workspace["blocked"] = True
    workspace["blocked_reason"] = reason.strip()
    saved = _save_workspace(workspace)
    append_audit_entry(
        actor=actor,
        agent="security_agent",
        action="block_workspace",
        target=workspace_id,
        status_value="success",
        risk_level="high",
        details={"reason": reason},
    )
    return saved


def unblock_workspace(workspace_id: str, actor: str, reason: str | None = None) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    workspace["blocked"] = False
    workspace["blocked_reason"] = None
    saved = _save_workspace(workspace)
    append_audit_entry(
        actor=actor,
        agent="security_agent",
        action="unblock_workspace",
        target=workspace_id,
        status_value="success",
        risk_level="medium",
        details={"reason": reason},
    )
    return saved


def list_admin_modules() -> list[dict[str, Any]]:
    return list_modules()


def toggle_module_sandbox(module_id: str, enabled: bool, actor: str, reason: str | None = None) -> dict[str, Any]:
    get_module(module_id)
    state = _load_runtime_state()
    state["module_toggles"][module_id] = bool(enabled)
    _save_runtime_state(state)
    append_audit_entry(
        actor=actor,
        agent="module_agent",
        action="toggle_module_sandbox",
        target=module_id,
        status_value="success",
        risk_level="medium",
        details={"enabled": enabled, "reason": reason},
    )
    return get_module(module_id)


def route_agent_task(
    task: str,
    actor: str = "system",
    workspace_id: str = "sandbox_workspace",
    agent_id: str | None = None,
    confirm_dangerous_action: bool = False,
) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)
    if workspace.get("blocked"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace is blocked.")

    selected_agent = agent_id
    if not selected_agent:
        lowered = task.lower()
        if any(token in lowered for token in ("stripe", "billing", "credits", "checkout", "subscription", "portal")):
            selected_agent = "billing_agent"
        elif any(token in lowered for token in ("module", "plan access", "entitlement")):
            selected_agent = "module_agent"
        elif any(token in lowered for token in ("secret", "security", "permission", "audit")):
            selected_agent = "security_agent"
        elif any(token in lowered for token in ("memory", "summary", "context")):
            selected_agent = "memory_agent"
        elif any(token in lowered for token in ("support", "faq", "client")):
            selected_agent = "support_agent"
        elif any(token in lowered for token in ("pricing", "product", "roadmap")):
            selected_agent = "product_agent"
        elif any(token in lowered for token in ("docker", "dns", "ssl", "cloudflare", "deploy")):
            selected_agent = "devops_agent"
        else:
            selected_agent = "orchestrator"

    if selected_agent not in _catalog_agents_by_id():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown agent: {selected_agent}")

    lowered_task = task.lower()
    dangerous = any(keyword in lowered_task for keyword in DANGEROUS_ACTION_KEYWORDS)
    if dangerous and settings.DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION and not confirm_dangerous_action:
        append_audit_entry(
            actor=actor,
            agent="orchestrator",
            action="route_agent_task",
            target=selected_agent,
            status_value="blocked",
            risk_level="high",
            details={"task": task, "reason": "confirmation_required"},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dangerous sandbox action requires confirmation.",
        )

    result = {
        "status": "executed",
        "task": task,
        "workspace_id": workspace_id,
        "routed_by": "orchestrator",
        "selected_agent": selected_agent,
        "confirm_dangerous_action": confirm_dangerous_action,
    }
    append_audit_entry(
        actor=actor,
        agent="orchestrator",
        action="route_agent_task",
        target=selected_agent,
        status_value="success",
        risk_level="medium" if dangerous else "low",
        details={"task": task, "workspace_id": workspace_id},
    )
    return result


def run_bot(
    bot_id: str,
    workspace_id: str = "sandbox_workspace",
    actor: str = "bot",
    task: str | None = None,
    confirm_dangerous_action: bool = False,
) -> dict[str, Any]:
    if not settings.BOTS_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bots are disabled in sandbox.")

    bot = _catalog_bots_by_id().get(bot_id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown bot: {bot_id}")
    if not bool(bot.get("enabled", True)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Bot {bot_id} is disabled.")

    resolved_task = task or bot.get("default_task") or f"Run sandbox bot {bot_id}"
    routed = route_agent_task(
        task=resolved_task,
        actor=actor,
        workspace_id=workspace_id,
        agent_id="orchestrator",
        confirm_dangerous_action=confirm_dangerous_action,
    )
    run = {
        "id": f"botrun_{uuid4().hex[:12]}",
        "bot_id": bot_id,
        "workspace_id": workspace_id,
        "task": resolved_task,
        "result": routed,
        "created_at": _utcnow(),
    }
    state = _load_runtime_state()
    state["bot_runs"].append(run)
    _save_runtime_state(state)
    append_audit_entry(
        actor=actor,
        agent="orchestrator",
        action="run_bot",
        target=bot_id,
        status_value="success",
        risk_level="low",
        details={"workspace_id": workspace_id},
    )
    return run


def get_status() -> dict[str, Any]:
    workspaces = list_workspaces()
    entitlements = [get_entitlements(workspace["id"]) for workspace in workspaces]
    total_revenue = round(sum(item["usage"]["monthly_revenue_usd"] for item in entitlements), 2)
    total_openai_cost = round(sum(item["usage"]["estimated_openai_cost_usd"] for item in entitlements), 6)
    total_margin = round(total_revenue - total_openai_cost, 6)

    return {
        "app_env": settings.APP_ENV,
        "app_name": settings.APP_NAME,
        "stripe_mode": settings.STRIPE_MODE,
        "catalog_loaded": True,
        "workspaces": len(workspaces),
        "blocked_workspaces": len([workspace for workspace in workspaces if workspace.get("blocked")]),
        "audit_entries": len(read_audit_entries(limit=500)),
        "modules": len(list_modules()),
        "agents": len(list_agents()),
        "bots": len(list_bots()),
        "profitability": {
            "monthly_revenue_usd": total_revenue,
            "estimated_openai_cost_usd": total_openai_cost,
            "gross_margin_usd": total_margin,
            "target_margin_pct": getattr(settings, "OPENAI_TARGET_GROSS_MARGIN_PCT", 70),
        },
        "stripe_catalog_ready": {
            "starter": bool(getattr(settings, "STRIPE_PRICE_STARTER_MONTHLY_ID", "")),
            "pro": bool(getattr(settings, "STRIPE_PRICE_PRO_MONTHLY_ID", "")),
            "business": bool(getattr(settings, "STRIPE_PRICE_BUSINESS_MONTHLY_ID", "")),
        },
        "guards": {
            "live_keys_allowed": settings.SANDBOX_ALLOW_LIVE_KEYS,
            "dangerous_actions_require_confirmation": settings.DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION,
            "openai_cost_guard_enabled": getattr(settings, "OPENAI_COST_GUARD_ENABLED", True),
        },
    }
