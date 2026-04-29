"""
backend/api/routers/knowledge_weapon.py — Module 6: Knowledge Weapon

  POST /knowledge/extract  — extract structured action plan from content (auth required)
  GET  /knowledge/history  — list user's past results (auth required)
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from api.core.deps import CurrentUser, DB, require_module_access, require_usage_budget
from api.services.knowledge_weapon_service import run_knowledge_weapon
from api.services.usage_service import record_usage

logger = logging.getLogger(__name__)
router = APIRouter()


class KnowledgeWeaponRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=8000, description="Input content")
    context: str | None = Field(None, max_length=2000)


class KnowledgeWeaponResponse(BaseModel):
    result: str
    module: str = "knowledge_weapon"


@router.post("/knowledge/extract", response_model=KnowledgeWeaponResponse, status_code=status.HTTP_201_CREATED)
async def extract_knowledge_weapon(
    body: KnowledgeWeaponRequest,
    current_user: CurrentUser,
    db: DB,
    _module_access: Annotated[CurrentUser, Depends(require_module_access("knowledge"))],
    _usage_budget: Annotated[tuple[bool, str], Depends(require_usage_budget())],
):
    result, tokens = await run_knowledge_weapon(body.content, body.context or "")
    await record_usage(current_user.id, "knowledge_weapon", tokens, db)
    return KnowledgeWeaponResponse(result=result)
