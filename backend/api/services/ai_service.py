from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from api.config import settings

ROOT_DIR = Path(__file__).resolve().parents[3]
PROMPTS_DIR = ROOT_DIR / "packages" / "ai" / "prompts"
POLICIES_DIR = ROOT_DIR / "packages" / "ai" / "policies"
SCHEMAS_DIR = ROOT_DIR / "packages" / "ai" / "schemas"
_SAFE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _state_root() -> Path:
    configured = str(getattr(settings, "AI_STATE_DIR", "") or "").strip()
    return Path(configured) if configured else ROOT_DIR / "data"


def _safe_identifier(value: str, *, field_name: str) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) < 3 or len(cleaned) > 64 or any(char not in _SAFE_ID_CHARS for char in cleaned):
        raise ValueError(f"Unsafe {field_name}.")
    return cleaned


AI_DATA_DIR = _state_root() / "ai"
MEMORY_ROOT = _state_root() / "memory"
AUDIT_LOG_PATH = _state_root() / "audit" / "ai-audit.jsonl"
CONVERSATIONS_PATH = AI_DATA_DIR / "conversations.json"
USAGE_EVENTS_PATH = AI_DATA_DIR / "usage-events.json"
LEARNING_EVENTS_PATH = AI_DATA_DIR / "learning-events.json"
PROMPT_GOVERNANCE_PATH = AI_DATA_DIR / "prompt-governance.json"
TENANT_PROFILES_PATH = AI_DATA_DIR / "tenant-profiles.json"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_runtime_layout() -> None:
    for directory in (
        PROMPTS_DIR,
        POLICIES_DIR,
        SCHEMAS_DIR,
        AI_DATA_DIR,
        MEMORY_ROOT / "master",
        MEMORY_ROOT / "tenants",
        MEMORY_ROOT / "shared_learning",
        AUDIT_LOG_PATH.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    for path, default in (
        (CONVERSATIONS_PATH, []),
        (USAGE_EVENTS_PATH, []),
        (LEARNING_EVENTS_PATH, []),
        (PROMPT_GOVERNANCE_PATH, []),
        (TENANT_PROFILES_PATH, {}),
    ):
        if not path.exists():
            write_json(path, default)


def read_json(path: Path, default: Any) -> Any:
    ensure_runtime_layout()
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def append_json_list(path: Path, item: dict[str, Any]) -> dict[str, Any]:
    payload = read_json(path, [])
    payload.append(item)
    write_json(path, payload)
    return item


def append_jsonl(path: Path, item: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=True) + "\n")
    return item


def tenant_memory_dir(tenant_id: str) -> Path:
    return MEMORY_ROOT / "tenants" / _safe_identifier(tenant_id, field_name="tenant_id")


def tenant_memory_path(tenant_id: str) -> Path:
    return tenant_memory_dir(tenant_id) / "memory.json"


def master_memory_path() -> Path:
    return MEMORY_ROOT / "master" / "memory.json"


def shared_learning_path() -> Path:
    return MEMORY_ROOT / "shared_learning" / "events.json"


def list_memory(scope: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    if scope == "master":
        return read_json(master_memory_path(), [])
    if scope == "shared_learning":
        return read_json(shared_learning_path(), [])
    if not tenant_id:
        return []
    return read_json(tenant_memory_path(tenant_id), [])


def save_memory(scope: str, content: str, *, tenant_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    target_path = master_memory_path() if scope == "master" else shared_learning_path() if scope == "shared_learning" else tenant_memory_path(str(tenant_id))
    item = {
        "id": f"mem_{uuid4().hex[:12]}",
        "scope": scope,
        "tenant_id": tenant_id,
        "memory_type": "note",
        "content": content.strip(),
        "metadata": metadata or {},
        "sensitivity_level": "restricted" if scope in {"master", "tenant"} else "anonymized",
        "created_at": utcnow(),
    }
    payload = read_json(target_path, [])
    payload.append(item)
    write_json(target_path, payload)
    return item


def search_memory(scope: str, query: str, *, tenant_id: str | None = None) -> list[dict[str, Any]]:
    normalized = query.strip().lower()
    return [
        item
        for item in list_memory(scope, tenant_id)
        if normalized in json.dumps(item, ensure_ascii=False).lower()
    ]


def load_profiles() -> dict[str, dict[str, Any]]:
    data = read_json(TENANT_PROFILES_PATH, {})
    return data if isinstance(data, dict) else {}


def save_profiles(profiles: dict[str, dict[str, Any]]) -> None:
    write_json(TENANT_PROFILES_PATH, profiles)


def _profile_key(tenant_id: str, workspace_id: str | None = None) -> str:
    safe_tenant_id = _safe_identifier(tenant_id, field_name="tenant_id")
    if not workspace_id:
        return safe_tenant_id
    return f"{safe_tenant_id}::{_safe_identifier(workspace_id, field_name='workspace_id')}"

def get_profile(tenant_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
    profiles = load_profiles()
    key = _profile_key(tenant_id, workspace_id)
    if key in profiles:
        return profiles[key]
    if workspace_id is None and tenant_id in profiles:
        return profiles[tenant_id]
    matches = [
        profile
        for profile in profiles.values()
        if profile.get("tenant_id") == tenant_id and (workspace_id is None or profile.get("workspace_id") == workspace_id)
    ]
    return matches[0] if len(matches) == 1 else None


def upsert_profile(tenant_id: str, profile: dict[str, Any], workspace_id: str | None = None) -> dict[str, Any]:
    profiles = load_profiles()
    profiles[_profile_key(tenant_id, workspace_id or str(profile.get("workspace_id", "") or ""))] = profile
    save_profiles(profiles)
    return profile


def estimate_tokens(*parts: Any) -> int:
    text = " ".join(str(part or "") for part in parts)
    if not text.strip():
        return 0
    return max(1, math.ceil(len(text) / 4))


def _conversation_store() -> list[dict[str, Any]]:
    data = read_json(CONVERSATIONS_PATH, [])
    return data if isinstance(data, list) else []


def get_or_create_conversation(owner_type: str, *, tenant_id: str | None, user_id: str | None, title: str | None = None) -> dict[str, Any]:
    conversations = _conversation_store()
    for item in reversed(conversations):
        if item.get("owner_type") == owner_type and item.get("tenant_id") == tenant_id and item.get("user_id") == user_id:
            return item

    conversation = {
        "id": f"conv_{uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "owner_type": owner_type,
        "user_id": user_id,
        "title": title or "Nanovia AI conversation",
        "created_at": utcnow(),
        "messages": [],
    }
    conversations.append(conversation)
    write_json(CONVERSATIONS_PATH, conversations)
    return conversation


def append_conversation_message(conversation_id: str, role: str, content: str, *, input_tokens: int = 0, output_tokens: int = 0, cost_estimate: float = 0.0) -> dict[str, Any]:
    conversations = _conversation_store()
    for item in conversations:
        if item.get("id") != conversation_id:
            continue
        message = {
            "id": f"msg_{uuid4().hex[:12]}",
            "role": role,
            "content": content,
            "token_input": input_tokens,
            "token_output": output_tokens,
            "cost_estimate": cost_estimate,
            "created_at": utcnow(),
        }
        item.setdefault("messages", []).append(message)
        write_json(CONVERSATIONS_PATH, conversations)
        return message
    raise KeyError(f"Conversation not found: {conversation_id}")


def conversation_messages(conversation_id: str) -> list[dict[str, Any]]:
    for item in _conversation_store():
        if item.get("id") == conversation_id:
            return list(item.get("messages", []))
    return []


def record_usage_event(event: dict[str, Any]) -> dict[str, Any]:
    return append_json_list(USAGE_EVENTS_PATH, event)


def usage_events() -> list[dict[str, Any]]:
    data = read_json(USAGE_EVENTS_PATH, [])
    return data if isinstance(data, list) else []


def record_learning_event(event: dict[str, Any]) -> dict[str, Any]:
    append_json_list(LEARNING_EVENTS_PATH, event)
    append_json_list(shared_learning_path(), event)
    return event


def learning_events() -> list[dict[str, Any]]:
    data = read_json(LEARNING_EVENTS_PATH, [])
    return data if isinstance(data, list) else []


def record_prompt_update(event: dict[str, Any]) -> dict[str, Any]:
    return append_json_list(PROMPT_GOVERNANCE_PATH, event)


def log_audit(scope: str, action: str, *, tenant_id: str | None, user_id: str | None, model: str, input_tokens: int, output_tokens: int, estimated_cost_usd: float, credits_charged: int, status_value: str, reason: str | None = None) -> dict[str, Any]:
    entry = {
        "timestamp": utcnow(),
        "environment": settings.APP_ENV,
        "scope": scope,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "model": model,
        "action": action,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "credits_charged": credits_charged,
        "status": status_value,
        "reason": reason,
    }
    append_jsonl(AUDIT_LOG_PATH, entry)
    return entry


def render_tenant_response(*, message: str, profile: dict[str, Any], route_preview: dict[str, Any], context: dict[str, Any]) -> str:
    allowed_modules = ", ".join(context.get("allowed_modules", [])) or "none"
    memory_summary = context.get("memory_summary") or "No private tenant memory yet."
    return (
        f"Nanovia tenant AI for {profile['display_name']} routed this request to "
        f"{route_preview['selected_agent_name']} ({route_preview['selected_agent_key']}). "
        f"Allowed modules: {allowed_modules}. "
        f"Private memory summary: {memory_summary} "
        f"Response focus: {message.strip()}"
    )


def render_master_response(*, message: str, context: dict[str, Any]) -> str:
    usage = context.get("global_usage", {})
    learning = context.get("learning_summary") or "No shared learning yet."
    return (
        "Nanovia master AI reviewed the cross-tenant control plane. "
        f"Tracked scopes: {usage.get('scopes', {})}. "
        f"Learning summary: {learning} "
        f"Requested action: {message.strip()}"
    )
