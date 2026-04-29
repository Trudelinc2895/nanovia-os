"""
backend/api/routers/offer_generator.py — Module 9: Offer Generator

  POST /offer/generate  — generate an irresistible offer (auth required)
  GET  /offer/history   — list user's past results (auth required)
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from api.core.deps import CurrentUser, DB, require_module_access, require_usage_budget
from api.services.offer_generator_service import run_offer_generator
from api.services.usage_service import record_usage

logger = logging.getLogger(__name__)
router = APIRouter()


class OfferGeneratorRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=8000, description="Input content")
    context: str | None = Field(None, max_length=2000)


class OfferGeneratorResponse(BaseModel):
    result: str
    module: str = "offer_generator"


@router.post("/offer/generate", response_model=OfferGeneratorResponse, status_code=status.HTTP_201_CREATED)
async def generate_offer_generator(
    body: OfferGeneratorRequest,
    current_user: CurrentUser,
    db: DB,
    _module_access: Annotated[CurrentUser, Depends(require_module_access("offer"))],
    _usage_budget: Annotated[tuple[bool, str], Depends(require_usage_budget())],
):
    result, tokens = await run_offer_generator(body.content, body.context or "")
    await record_usage(current_user.id, "offer_generator", tokens, db)
    return OfferGeneratorResponse(result=result)
