"""
backend/api/routers/content_cloner.py — Module 2 Content Cloner endpoints

  POST /content-cloner/clone         — generate 5 formats from source content (auth)
  GET  /content-cloner/history       — list user's past clones, paginated (auth)
  GET  /content-cloner/history/{id}  — retrieve a specific clone (auth)
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from api.config import settings
from api.core.deps import CurrentUser, DB
from api.models.content_clone import ContentClone
from api.schemas.content_cloner import (
    CloneHistoryResponse,
    CloneListItem,
    CloneRequest,
    CloneResponse,
    CloneFormats,
)
from api.services.content_cloner_service import clone_content
from api.services.usage_service import check_and_charge_usage

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Clone ────────────────────────────────────────────────────────────────────

@router.post("/content-cloner/clone", response_model=CloneResponse, status_code=status.HTTP_201_CREATED)
async def create_clone(body: CloneRequest, current_user: CurrentUser, db: DB):
    """
    Transform original_content into 5 platform-optimised formats via OpenAI.
    Persists the result and returns it immediately.
    """
    # Enforce feature gate: Content Cloner requires api_access (pro+)
    from api.services.billing_service import has_feature
    if not has_feature(current_user.plan, "api_access"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Content Cloner nécessite un plan Pro ou supérieur.",
        )

    # Enforce usage quota (overage → credit deduction)
    within_limit, _ = await check_and_charge_usage(current_user, db)
    if not within_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Limite mensuelle atteinte. Upgrade ton plan pour continuer.",
        )

    formats = await clone_content(
        original=body.original_content,
        niche=body.niche,
        openai_key=settings.OPENAI_API_KEY,
    )

    clone = ContentClone(
        user_id=current_user.id,
        original_content=body.original_content,
        source_url=body.source_url,
        niche=body.niche,
        formats=formats,
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)

    logger.info(f"[content_cloner] Clone {clone.id} created for user {current_user.id}")
    return CloneResponse(
        id=clone.id,
        original_content=clone.original_content,
        source_url=clone.source_url,
        niche=clone.niche,
        formats=CloneFormats(**clone.formats),
        created_at=clone.created_at,
    )


# ─── History ──────────────────────────────────────────────────────────────────

@router.get("/content-cloner/history", response_model=CloneHistoryResponse)
async def list_history(
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Return paginated list of the authenticated user's past content clones."""
    base_filter = ContentClone.user_id == current_user.id

    total_result = await db.execute(
        select(func.count()).select_from(ContentClone).where(base_filter)
    )
    total = total_result.scalar_one()

    rows_result = await db.execute(
        select(ContentClone)
        .where(base_filter)
        .order_by(ContentClone.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    clones = rows_result.scalars().all()

    items = [
        CloneListItem(
            id=c.id,
            niche=c.niche,
            source_url=c.source_url,
            created_at=c.created_at,
            original_preview=c.original_content[:120] + ("…" if len(c.original_content) > 120 else ""),
        )
        for c in clones
    ]

    return CloneHistoryResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/content-cloner/history/{clone_id}", response_model=CloneResponse)
async def get_clone(clone_id: uuid.UUID, current_user: CurrentUser, db: DB):
    """Retrieve a specific content clone by ID (must belong to the authenticated user)."""
    result = await db.execute(
        select(ContentClone).where(
            ContentClone.id == clone_id,
            ContentClone.user_id == current_user.id,
        )
    )
    clone = result.scalar_one_or_none()
    if clone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clone not found")

    return CloneResponse(
        id=clone.id,
        original_content=clone.original_content,
        source_url=clone.source_url,
        niche=clone.niche,
        formats=CloneFormats(**clone.formats),
        created_at=clone.created_at,
    )
