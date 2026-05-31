from __future__ import annotations

from typing import Any

from api.services import ai_service, learning_service


def build_tenant_context(*, tenant_id: str, profile: dict[str, Any], message: str, context_limit: int) -> dict[str, Any]:
    memory_items = ai_service.list_memory("tenant", tenant_id=tenant_id)[-context_limit:]
    return {
        "tenant_id": tenant_id,
        "display_name": profile.get("display_name"),
        "plan": profile.get("plan"),
        "allowed_modules": list(profile.get("allowed_modules", [])),
        "allowed_tools": list(profile.get("allowed_tools", [])),
        "memory_items": memory_items,
        "memory_summary": " | ".join(item["content"][:120] for item in memory_items[-3:]) if memory_items else "",
        "message": message,
    }


def build_master_context(*, message: str, usage: dict[str, Any], context_limit: int) -> dict[str, Any]:
    memory_items = ai_service.list_memory("master")[-context_limit:]
    learning_items = learning_service.list_learning()[-context_limit:]
    return {
        "message": message,
        "master_memory": memory_items,
        "learning_items": learning_items,
        "learning_summary": " | ".join(item["insight"][:120] for item in learning_items[-3:]) if learning_items else "",
        "global_usage": usage,
    }
