from __future__ import annotations

from copy import deepcopy
from typing import Any

from api.services import ai_service

DEFAULT_MODEL_POLICY: dict[str, Any] = {
    "credit_value_usd": 0.01,
    "minimum_markup_multiplier": 3.0,
    "ideal_markup_range": [4.0, 6.0],
    "plans": {
        "starter": {
            "default_model": "gpt-5.4-mini",
            "fallback_model": "gpt-5.4",
            "max_monthly_credits": 1000,
            "max_context_messages": 10,
            "tools_enabled": False,
            "memory_enabled": False,
        },
        "pro": {
            "default_model": "gpt-5.4-mini",
            "fallback_model": "gpt-5.4",
            "max_monthly_credits": 5000,
            "max_context_messages": 30,
            "tools_enabled": True,
            "memory_enabled": True,
        },
        "business": {
            "default_model": "gpt-5.4",
            "fallback_model": "gpt-5.5",
            "max_monthly_credits": 20000,
            "max_context_messages": 60,
            "tools_enabled": True,
            "memory_enabled": True,
        },
        "owner": {
            "default_model": "gpt-5.5",
            "fallback_model": "gpt-5.4",
            "max_monthly_credits": 100000,
            "max_context_messages": 80,
            "tools_enabled": True,
            "memory_enabled": True,
        },
    },
}


def load_model_policy() -> dict[str, Any]:
    payload = ai_service.read_json(ai_service.POLICIES_DIR / "model-policy.json", deepcopy(DEFAULT_MODEL_POLICY))
    if not isinstance(payload, dict) or "plans" not in payload:
        return deepcopy(DEFAULT_MODEL_POLICY)
    return payload


def plan_policy(plan: str) -> dict[str, Any]:
    policy = load_model_policy()
    normalized = (plan or "starter").lower()
    return dict(policy["plans"].get(normalized, policy["plans"]["starter"]))


def select_model(plan: str, *, prefer_fallback: bool = False) -> str:
    entry = plan_policy(plan)
    if prefer_fallback and entry.get("fallback_model"):
        return str(entry["fallback_model"])
    return str(entry["default_model"])


def tools_enabled(plan: str) -> bool:
    return bool(plan_policy(plan).get("tools_enabled", False))


def memory_enabled(plan: str) -> bool:
    return bool(plan_policy(plan).get("memory_enabled", False))


def max_context_messages(plan: str) -> int:
    return int(plan_policy(plan).get("max_context_messages", 10))


def credit_value_usd() -> float:
    return float(load_model_policy().get("credit_value_usd", 0.01))


def minimum_markup_multiplier() -> float:
    return float(load_model_policy().get("minimum_markup_multiplier", 3.0))
