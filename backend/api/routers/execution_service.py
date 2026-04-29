"""
backend/api/routers/execution_service.py — Module 10: Execution Service

  POST /execution/plan   — transform idea into executable plan (auth required)
  GET  /execution/history — list user's past results (auth required)
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from api.core.deps import CurrentUser, DB, require_module_access, require_usage_budget
from api.services.execution_service_service import run_execution_service
from api.services.usage_service import record_usage

logger = logging.getLogger(__name__)
router = APIRouter()


class ExecutionServiceRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=8000, description="Input content")
    context: str | None = Field(None, max_length=2000)


class ExecutionServiceResponse(BaseModel):
    result: str
    module: str = "execution_service"


@router.post("/execution/plan", response_model=ExecutionServiceResponse, status_code=status.HTTP_201_CREATED)
async def plan_execution_service(
    body: ExecutionServiceRequest,
    current_user: CurrentUser,
    db: DB,
    _module_access: Annotated[CurrentUser, Depends(require_module_access("execution"))],
    _usage_budget: Annotated[tuple[bool, str], Depends(require_usage_budget())],
):
    result, tokens = await run_execution_service(body.content, body.context or "")
    await record_usage(current_user.id, "execution_service", tokens, db)
    return ExecutionServiceResponse(result=result)
