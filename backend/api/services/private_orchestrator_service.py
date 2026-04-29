"""Private/admin-only orchestrator scaffold for Nanovia."""
from __future__ import annotations

from typing import Any

import httpx

from api.config import settings

PRIVATE_ORCHESTRATOR_CONTEXT_KEY = "nanovia-private-admin-orchestrator"
PRIVATE_ORCHESTRATOR_ENDPOINTS = [
    "/api/v1/admin/orchestrator/overview",
    "/api/v1/admin/orchestrator/agents",
    "/api/v1/admin/orchestrator/preview",
]

_DEFAULT_AGENT_CATALOG: dict[str, dict[str, str]] = {
    "operator": {
        "name": "AI Personal Operator",
        "description": "Assistant executif pour organisation, priorites et operations.",
    },
    "ghost_agency": {
        "name": "Ghost Automation Agency",
        "description": "Prospection et sequences commerciales admin-only en contexte prive.",
    },
    "decision_engine": {
        "name": "AI Decision Engine",
        "description": "Analyse de scenarios et arbitrages operationnels.",
    },
}

_AGENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "operator": (
        "organize", "prioritize", "plan", "task", "workflow", "schedule", "email", "assistant",
        "operate", "automation", "coordinate", "follow-up",
    ),
    "ghost_agency": (
        "lead", "prospect", "outreach", "campaign", "sales", "sequence", "cold", "crm",
        "acquisition", "funnel", "contact",
    ),
    "decision_engine": (
        "decide", "compare", "scenario", "risk", "tradeoff", "option", "strategy", "analysis",
        "forecast", "recommendation", "prioritization", "arbitrage",
    ),
}

_INTENT_HINTS: dict[str, tuple[str, ...]] = {
    "sales-outreach": _AGENT_KEYWORDS["ghost_agency"],
    "decision-support": _AGENT_KEYWORDS["decision_engine"],
    "operations-assistant": _AGENT_KEYWORDS["operator"],
}


def get_allowed_agent_keys() -> list[str]:
    configured = settings.PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS or list(_DEFAULT_AGENT_CATALOG)
    filtered: list[str] = []
    for key in configured:
        if key in _DEFAULT_AGENT_CATALOG and key not in filtered:
            filtered.append(key)
    return filtered or list(_DEFAULT_AGENT_CATALOG)


def get_static_agent_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "name": _DEFAULT_AGENT_CATALOG[key]["name"],
            "description": _DEFAULT_AGENT_CATALOG[key]["description"],
            "allowed": True,
        }
        for key in get_allowed_agent_keys()
    ]


def _normalize_text(value: str) -> str:
    return " ".join((value or "").lower().split())


def build_memory_snapshot(messages: list[dict[str, Any]] | None, *, limit: int = 6) -> dict[str, Any]:
    history = messages or []
    recent = history[-limit:]
    recent_messages = [
        {
            "role": str(item.get("role", "unknown")),
            "content": str(item.get("content", ""))[:240],
        }
        for item in recent
        if item.get("content")
    ]
    if not recent_messages:
        summary = "No prior conversation context."
    else:
        summary = " | ".join(
            f"{item['role']}: {item['content'][:80]}"
            for item in recent_messages[-3:]
        )
    return {
        "message_count": len(history),
        "recent_messages": recent_messages,
        "summary": summary,
    }


def classify_intent(message: str) -> str:
    normalized = _normalize_text(message)
    for intent, keywords in _INTENT_HINTS.items():
        if any(keyword in normalized for keyword in keywords):
            return intent
    return "general-assistant"


def _capabilities_for_message(message: str) -> list[str]:
    normalized = _normalize_text(message)
    capabilities: list[str] = ["conversation-memory", "agent-routing"]
    if any(keyword in normalized for keyword in _AGENT_KEYWORDS["ghost_agency"]):
        capabilities.extend(["sales-automation", "outreach-planning"])
    if any(keyword in normalized for keyword in _AGENT_KEYWORDS["decision_engine"]):
        capabilities.extend(["scenario-analysis", "result-scoring"])
    if any(keyword in normalized for keyword in _AGENT_KEYWORDS["operator"]):
        capabilities.extend(["task-planning", "workflow-routing"])
    ordered: list[str] = []
    for capability in capabilities:
        if capability not in ordered:
            ordered.append(capability)
    return ordered


def score_agents(
    message: str,
    *,
    allowed_agent_keys: list[str] | None = None,
    force_agent: str | None = None,
) -> list[dict[str, Any]]:
    normalized = _normalize_text(message)
    allowed = allowed_agent_keys or get_allowed_agent_keys()
    catalog = {agent["key"]: agent for agent in get_static_agent_catalog()}
    scored: list[dict[str, Any]] = []

    for key in allowed:
        if key not in catalog:
            continue
        score = 0.2
        reasons: list[str] = []
        keyword_hits = [keyword for keyword in _AGENT_KEYWORDS.get(key, ()) if keyword in normalized]
        if keyword_hits:
            score += min(0.5, 0.12 * len(keyword_hits))
            reasons.append(f"keyword match: {', '.join(keyword_hits[:3])}")
        if key == "operator":
            score += 0.15
            reasons.append("default safe fallback")
        if force_agent and force_agent == key:
            score = 1.0
            reasons = ["forced by caller"]
        scored.append(
            {
                "key": key,
                "name": catalog[key]["name"],
                "score": round(min(score, 1.0), 3),
                "reasons": reasons or ["eligible allowlisted agent"],
            }
        )

    return sorted(scored, key=lambda item: (-item["score"], item["key"]))


async def build_route_preview(
    message: str,
    *,
    conversation_messages: list[dict[str, Any]] | None = None,
    force_agent: str | None = None,
    allowed_agent_keys: list[str] | None = None,
) -> dict[str, Any]:
    candidates = score_agents(
        message,
        allowed_agent_keys=allowed_agent_keys or get_allowed_agent_keys(),
        force_agent=force_agent,
    )
    if not candidates:
        candidates = score_agents(message, allowed_agent_keys=get_allowed_agent_keys())
    selected = candidates[0]
    memory = build_memory_snapshot(conversation_messages)
    return {
        "selected_agent_key": selected["key"],
        "selected_agent_name": selected["name"],
        "confidence": selected["score"],
        "force_agent_applied": bool(force_agent and force_agent == selected["key"]),
        "intent": classify_intent(message),
        "required_capabilities": _capabilities_for_message(message),
        "memory": memory,
        "candidates": candidates,
        "upstream": await fetch_upstream_health(),
    }


async def fetch_upstream_health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.PRIVATE_ORCHESTRATOR_UPSTREAM_URL}/health")
            response.raise_for_status()
            data = response.json()
        return {
            "ok": data.get("status") == "ok",
            "status": str(data.get("status", "unknown")),
            "service": data.get("service"),
            "version": data.get("version"),
            "detail": None,
        }
    except httpx.TimeoutException:
        return {
            "ok": False,
            "status": "timeout",
            "service": None,
            "version": None,
            "detail": "Timed out while contacting the private orchestrator upstream.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "unavailable",
            "service": None,
            "version": None,
            "detail": str(exc),
        }


async def fetch_upstream_agents() -> tuple[list[dict[str, Any]], str]:
    allowed_keys = set(get_allowed_agent_keys())
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.PRIVATE_ORCHESTRATOR_UPSTREAM_URL}/agents")
            response.raise_for_status()
            payload = response.json()

        agents = [
            {
                "key": item["key"],
                "name": item["name"],
                "description": item["description"],
                "allowed": True,
            }
            for item in payload
            if item.get("key") in allowed_keys
        ]
        return (agents or get_static_agent_catalog(), "upstream")
    except Exception:
        return (get_static_agent_catalog(), "fallback")


async def build_private_orchestrator_overview() -> dict[str, Any]:
    upstream = await fetch_upstream_health()
    return {
        "context_key": PRIVATE_ORCHESTRATOR_CONTEXT_KEY,
        "enabled": settings.PRIVATE_ORCHESTRATOR_ENABLED,
        "release_stage": "private-beta",
        "access": {
            "admin_only": True,
            "feature_flagged": True,
            "public_saas_exposure": False,
            "destructive_merge_with_my_agent_hub": False,
            "requires_private_admin_surface": True,
            "production_ip_allowlist_required": True,
        },
        "capabilities": {
            "agent_catalog_read": True,
            "upstream_health_read": True,
            "planner_preview": True,
            "agent_routing": True,
            "conversation_memory": True,
            "result_scoring": True,
            "prompt_execution": False,
            "terminal_access": False,
            "filesystem_access": False,
            "browser_access": False,
            "billing_mutation": False,
            "user_impersonation": False,
        },
        "allowed_agent_keys": get_allowed_agent_keys(),
        "upstream": upstream,
        "endpoints": PRIVATE_ORCHESTRATOR_ENDPOINTS,
        "notes": [
            "Disabled by default via PRIVATE_ORCHESTRATOR_ENABLED.",
            "Admin-only surface; never link from public SaaS navigation.",
            "Planner preview, scored routing and bounded conversation-memory summary are enabled.",
            "No terminal, filesystem, browser, billing mutation or user impersonation capabilities in this slice.",
            "No destructive merge with my_agent_hub is performed here; this is isolated repo-side scaffolding only.",
        ],
    }
