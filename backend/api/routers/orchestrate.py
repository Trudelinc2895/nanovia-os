"""
backend/api/routers/orchestrate.py

POST /api/v1/orchestrate — Point d'entrée unique pour l'IA.
L'orchestrateur analyse l'intention et route vers le bon agent.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.config import settings
from api.core.deps import CurrentUser, DB, require_feature, require_usage_budget
from api.models.conversation import Conversation
from api.services import private_orchestrator_service
from api.services.usage_service import record_usage

logger = logging.getLogger(__name__)
router = APIRouter()

class OrchestrateRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    force_agent: str | None = None


class OrchestrateResponse(BaseModel):
    response: str
    agent_used: str
    agent_name: str
    confidence: float
    conversation_id: str
    session_id: str


@router.post("/orchestrate", response_model=OrchestrateResponse)
async def orchestrate(
    body: OrchestrateRequest,
    current_user: CurrentUser,
    db: DB,
    _feature_access: Annotated[CurrentUser, Depends(require_feature("automation"))],
    _usage_budget: Annotated[tuple[bool, str], Depends(require_usage_budget())],
):
    """
    Universal AI entry point.
    - Routes to the right agent based on intent
    - Persists conversation history
    - Enforces plan limits
    """
    # Get or create conversation
    conversation_id = body.conversation_id
    conversation: Conversation | None = None

    if conversation_id:
        from sqlalchemy import select
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == uuid.UUID(conversation_id),
                Conversation.user_id == current_user.id,
            )
        )
        conversation = result.scalar_one_or_none()

    if conversation is None:
        conversation = Conversation(
            user_id=current_user.id,
            title=body.message[:80],
            module="orchestrator",
            messages=[],
        )
        db.add(conversation)
        await db.flush()

    conversation_messages = list(conversation.messages or [])
    route_preview = await private_orchestrator_service.build_route_preview(
        body.message,
        conversation_messages=conversation_messages,
        force_agent=body.force_agent,
    )

    # Call orchestrator
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.PRIVATE_ORCHESTRATOR_UPSTREAM_URL}/route",
                json={
                    "message": body.message,
                    "session_id": str(conversation.id),
                    "user_id": str(current_user.id),
                    "force_agent": body.force_agent,
                    "route_plan": route_preview,
                    "memory": route_preview["memory"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI Orchestrator timeout. Réessaie.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Orchestrator error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"[orchestrate] Error: {e}")
        raise HTTPException(status_code=503, detail="AI Orchestrator unavailable. Configure OPENAI_API_KEY.")

    # Persist message to conversation
    messages = list(conversation.messages or [])
    messages.append({"role": "user", "content": body.message, "ts": str(uuid.uuid4())})
    messages.append({
        "role": "assistant",
        "content": data["response"],
        "agent": data.get("agent_used") or route_preview["selected_agent_key"],
        "route_preview": {
            "intent": route_preview["intent"],
            "confidence": route_preview["confidence"],
        },
        "ts": str(uuid.uuid4()),
    })
    conversation.messages = messages
    db.add(conversation)

    # Record usage (rough word-count token estimate)
    tokens_estimate = len(body.message.split()) + len(data["response"].split())
    await record_usage(current_user.id, "orchestrator", tokens_estimate, db)

    await db.commit()

    return OrchestrateResponse(
        response=data["response"],
        agent_used=data.get("agent_used") or route_preview["selected_agent_key"],
        agent_name=data.get("agent_name") or route_preview["selected_agent_name"],
        confidence=float(data.get("confidence", route_preview["confidence"])),
        conversation_id=str(conversation.id),
        session_id=data.get("session_id", str(conversation.id)),
    )


@router.get("/orchestrate/agents")
async def list_agents(current_user: CurrentUser):
    """List available agents."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.PRIVATE_ORCHESTRATOR_UPSTREAM_URL}/agents")
            return resp.json()
    except Exception:
        return [{"key": "operator", "name": "AI Personal Operator", "description": "Assistant personnel IA"}]
