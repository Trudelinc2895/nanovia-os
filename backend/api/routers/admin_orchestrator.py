"""Admin-only private orchestrator routes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.config import settings
from api.core.deps import AdminUser
from api.core.deps import DB
from api.models.conversation import Conversation
from api.schemas.private_orchestrator import (
    PrivateOrchestratorAgentsResponse,
    PrivateOrchestratorOverview,
    PrivateOrchestratorRoutePreview,
)
from api.services import private_orchestrator_service

router = APIRouter()


def _require_private_orchestrator_enabled() -> None:
    if not settings.PRIVATE_ORCHESTRATOR_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")


class PrivateOrchestratorPreviewRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    force_agent: str | None = None


@router.get("/orchestrator/overview", response_model=PrivateOrchestratorOverview)
async def admin_private_orchestrator_overview(_: AdminUser):
    """Return the bounded contract for the private orchestrator slice."""
    _require_private_orchestrator_enabled()
    return await private_orchestrator_service.build_private_orchestrator_overview()


@router.get("/orchestrator/agents", response_model=PrivateOrchestratorAgentsResponse)
async def admin_private_orchestrator_agents(_: AdminUser):
    """Return the allowlisted private/admin agent catalog."""
    _require_private_orchestrator_enabled()
    agents, source = await private_orchestrator_service.fetch_upstream_agents()
    return {
        "enabled": True,
        "source": source,
        "agents": agents,
    }


@router.post("/orchestrator/preview", response_model=PrivateOrchestratorRoutePreview)
async def admin_private_orchestrator_preview(
    body: PrivateOrchestratorPreviewRequest,
    _: AdminUser,
    db: DB,
):
    """Preview planner/routing output without executing any agent action."""
    _require_private_orchestrator_enabled()
    conversation_messages = None
    if body.conversation_id:
        try:
            conversation_uuid = uuid.UUID(body.conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid conversation_id") from exc
        result = await db.execute(select(Conversation).where(Conversation.id == conversation_uuid))
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conversation_messages = list(conversation.messages or [])

    preview = await private_orchestrator_service.build_route_preview(
        body.message,
        conversation_messages=conversation_messages,
        force_agent=body.force_agent,
    )
    preview["conversation_id"] = body.conversation_id
    return preview
