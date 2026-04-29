"""
backend/api/routers/reverse_engineering.py — Module 8: Reverse Engineering

  POST /reverse/analyze    — analyze competitor and generate replication playbook (auth required)
  GET  /reverse/history    — list user's past results (auth required)
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from api.core.deps import CurrentUser, DB, require_module_access, require_usage_budget
from api.services.reverse_engineering_service import run_reverse_engineering
from api.services.usage_service import record_usage

logger = logging.getLogger(__name__)
router = APIRouter()


class ReverseEngineeringRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=8000, description="Input content")
    context: str | None = Field(None, max_length=2000)


class ReverseEngineeringResponse(BaseModel):
    result: str
    module: str = "reverse_engineering"


@router.post("/reverse/analyze", response_model=ReverseEngineeringResponse, status_code=status.HTTP_201_CREATED)
async def analyze_reverse_engineering(
    body: ReverseEngineeringRequest,
    current_user: CurrentUser,
    db: DB,
    _module_access: Annotated[CurrentUser, Depends(require_module_access("reverse"))],
    _usage_budget: Annotated[tuple[bool, str], Depends(require_usage_budget())],
):
    result, tokens = await run_reverse_engineering(body.content, body.context or "")
    await record_usage(current_user.id, "reverse_engineering", tokens, db)
    return ReverseEngineeringResponse(result=result)
