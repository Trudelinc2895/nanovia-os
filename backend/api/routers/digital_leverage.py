"""
backend/api/routers/digital_leverage.py — Module 7: Digital Leverage

  POST /leverage/generate  — generate leverage strategy (auth required)
  GET  /leverage/history   — list user's past results (auth required)
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from api.core.deps import CurrentUser, DB, require_module_access, require_usage_budget
from api.services.digital_leverage_service import run_digital_leverage
from api.services.usage_service import record_usage

logger = logging.getLogger(__name__)
router = APIRouter()


class DigitalLeverageRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=8000, description="Input content")
    context: str | None = Field(None, max_length=2000)


class DigitalLeverageResponse(BaseModel):
    result: str
    module: str = "digital_leverage"


@router.post("/leverage/generate", response_model=DigitalLeverageResponse, status_code=status.HTTP_201_CREATED)
async def generate_digital_leverage(
    body: DigitalLeverageRequest,
    current_user: CurrentUser,
    db: DB,
    _module_access: Annotated[CurrentUser, Depends(require_module_access("leverage"))],
    _usage_budget: Annotated[tuple[bool, str], Depends(require_usage_budget())],
):
    result, tokens = await run_digital_leverage(body.content, body.context or "")
    await record_usage(current_user.id, "digital_leverage", tokens, db)
    return DigitalLeverageResponse(result=result)
