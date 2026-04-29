"""
backend/api/routers/decision_engine.py — Module 5: Decision Engine

  POST /decision/analyze   — analyze a situation and return structured decision (auth required)
  GET  /decision/history   — list user's past results (auth required)
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from api.core.deps import CurrentUser, DB, require_module_access, require_usage_budget
from api.services.decision_engine_service import run_decision_engine
from api.services.usage_service import record_usage

logger = logging.getLogger(__name__)
router = APIRouter()


class DecisionEngineRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=8000, description="Input content")
    context: str | None = Field(None, max_length=2000)


class DecisionEngineResponse(BaseModel):
    result: str
    module: str = "decision_engine"


@router.post("/decision/analyze", response_model=DecisionEngineResponse, status_code=status.HTTP_201_CREATED)
async def analyze_decision_engine(
    body: DecisionEngineRequest,
    current_user: CurrentUser,
    db: DB,
    _module_access: Annotated[CurrentUser, Depends(require_module_access("decision"))],
    _usage_budget: Annotated[tuple[bool, str], Depends(require_usage_budget())],
):
    result, tokens = await run_decision_engine(body.content, body.context or "")
    await record_usage(current_user.id, "decision_engine", tokens, db)
    return DecisionEngineResponse(result=result)
