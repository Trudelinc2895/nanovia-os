from __future__ import annotations

import math
from collections import Counter
from typing import Any

from api.services import ai_service, model_policy, sandbox_service

_MODEL_RATE_CARD = {
    "gpt-5-mini": {"input_per_million": 0.25, "output_per_million": 2.0},
    "gpt-5": {"input_per_million": 1.25, "output_per_million": 10.0},
}
_MODEL_ALIASES = {
    "gpt-5.4-mini": "gpt-5-mini",
    "gpt-5-mini": "gpt-5-mini",
    "gpt-5.4": "gpt-5",
    "gpt-5.5": "gpt-5",
    "gpt-5": "gpt-5",
}


def _normalized_model(model: str) -> str:
    return _MODEL_ALIASES.get(model, "gpt-5-mini")


def estimate_openai_cost(model: str, input_tokens: int, output_tokens: int, tool_calls: int = 0) -> float:
    rates = _MODEL_RATE_CARD[_normalized_model(model)]
    cost = ((max(input_tokens, 0) / 1_000_000) * rates["input_per_million"]) + ((max(output_tokens, 0) / 1_000_000) * rates["output_per_million"])
    return round(cost + (0.0025 * max(tool_calls, 0)), 6)


def quote_usage(plan: str, model: str, input_tokens: int, output_tokens: int, *, tool_calls: int = 0) -> dict[str, Any]:
    openai_cost = estimate_openai_cost(model, input_tokens, output_tokens, tool_calls)
    minimum_markup = max(model_policy.minimum_markup_multiplier(), 3.0)
    billable_cost = round(openai_cost * minimum_markup, 6)
    credits_charged = max(1, math.ceil(billable_cost / model_policy.credit_value_usd()))
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "estimated_openai_cost_usd": openai_cost,
        "markup_multiplier": minimum_markup,
        "billable_cost_usd": billable_cost,
        "credits_charged": credits_charged,
        "plan": plan,
    }


def record_tenant_usage(*, tenant_id: str, workspace_id: str, model: str, input_tokens: int, output_tokens: int, tool_calls: int = 0, reason: str = "tenant ai chat") -> dict[str, Any]:
    workspace = sandbox_service.get_workspace(workspace_id)
    plan = str(workspace.get("plan", "starter"))
    quote = quote_usage(plan, model, input_tokens, output_tokens, tool_calls=tool_calls)
    ledger = sandbox_service.record_usage(
        workspace_id=workspace_id,
        actor="tenant_ai",
        kind="tenant_ai_chat",
        model=model,
        units=quote["credits_charged"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reason=reason,
        credits_override=quote["credits_charged"],
    )
    event = {
        "id": ledger["event"]["id"],
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "scope": "tenant",
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "estimated_cost_usd": quote["estimated_openai_cost_usd"],
        "billable_cost_usd": quote["billable_cost_usd"],
        "credits_charged": quote["credits_charged"],
        "status": "success",
        "created_at": ai_service.utcnow(),
    }
    ai_service.record_usage_event(event)
    return {"quote": quote, "ledger": ledger, "event": event}


def record_master_usage(*, model: str, input_tokens: int, output_tokens: int, tool_calls: int = 0, reason: str = "master ai chat") -> dict[str, Any]:
    quote = quote_usage("owner", model, input_tokens, output_tokens, tool_calls=tool_calls)
    event = {
        "id": f"usage_master_{len(ai_service.usage_events()) + 1}",
        "tenant_id": None,
        "workspace_id": None,
        "scope": "master",
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "estimated_cost_usd": quote["estimated_openai_cost_usd"],
        "billable_cost_usd": quote["billable_cost_usd"],
        "credits_charged": 0,
        "status": "success",
        "reason": reason,
        "created_at": ai_service.utcnow(),
    }
    ai_service.record_usage_event(event)
    return {"quote": quote, "event": event}


def tenant_usage_summary(tenant_id: str, workspace_id: str) -> dict[str, Any]:
    events = [item for item in ai_service.usage_events() if item.get("tenant_id") == tenant_id or item.get("workspace_id") == workspace_id]
    return {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "events_count": len(events),
        "credits_charged": sum(int(item.get("credits_charged", 0)) for item in events),
        "estimated_cost_usd": round(sum(float(item.get("estimated_cost_usd", 0)) for item in events), 6),
        "models": Counter(str(item.get("model", "")) for item in events),
        "events": events[-50:],
    }


def global_usage_summary() -> dict[str, Any]:
    events = ai_service.usage_events()
    scopes = Counter(str(item.get("scope", "unknown")) for item in events)
    return {
        "events_count": len(events),
        "credits_charged": sum(int(item.get("credits_charged", 0)) for item in events),
        "estimated_cost_usd": round(sum(float(item.get("estimated_cost_usd", 0)) for item in events), 6),
        "scopes": dict(scopes),
        "events": events[-100:],
    }
