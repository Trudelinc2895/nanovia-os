"""
backend/api/routers/micro_saas.py — Module 3: Micro-SaaS Builder

  POST /micro-saas/build    — build a micro-SaaS plan (auth required)
  GET  /micro-saas/history  — list user's past results (auth required)
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from api.core.deps import CurrentUser, DB, require_module_access, require_usage_budget
from api.services.micro_saas_service import run_micro_saas
from api.services.usage_service import record_usage

logger = logging.getLogger(__name__)
router = APIRouter()


class MicroSaasRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=8000, description="Input content")
    context: str | None = Field(None, max_length=2000)


class MicroSaasResponse(BaseModel):
    result: str
    module: str = "micro_saas"


@router.post("/micro-saas/build", response_model=MicroSaasResponse, status_code=status.HTTP_201_CREATED)
async def build_micro_saas(
    body: MicroSaasRequest,
    current_user: CurrentUser,
    db: DB,
    _module_access: Annotated[CurrentUser, Depends(require_module_access("micro_saas"))],
    _usage_budget: Annotated[tuple[bool, str], Depends(require_usage_budget())],
):
    result, tokens = await run_micro_saas(body.content, body.context or "")
    await record_usage(current_user.id, "micro_saas", tokens, db)
    return MicroSaasResponse(result=result)
