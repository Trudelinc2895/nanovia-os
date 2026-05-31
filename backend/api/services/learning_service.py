from __future__ import annotations

from typing import Any
from uuid import uuid4

from api.services import ai_service, safety_guard


def extract_learning_event(*, source_scope: str, content: str, tenant_id: str | None = None, category: str | None = None, confidence: float = 0.75, frequency: int = 1) -> dict[str, Any]:
    cleaned = safety_guard.anonymize_learning_event(content)
    event = {
        "id": f"learn_{uuid4().hex[:12]}",
        "source_scope": source_scope,
        "tenant_id": None,
        "anonymized": True,
        "category": category or "general",
        "insight": cleaned,
        "confidence": round(float(confidence), 3),
        "frequency": int(frequency),
        "created_at": ai_service.utcnow(),
    }
    return ai_service.record_learning_event(event)


def list_learning() -> list[dict[str, Any]]:
    return ai_service.learning_events()
