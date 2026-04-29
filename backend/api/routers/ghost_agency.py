"""
backend/api/routers/ghost_agency.py — Module 4 Ghost Agency endpoints

  POST /ghost-agency/generate                          — generate personalized outreach message
  POST /ghost-agency/campaigns                         — create campaign
  GET  /ghost-agency/campaigns                         — list user's campaigns
  GET  /ghost-agency/campaigns/{campaign_id}/messages  — list messages in a campaign
  DELETE /ghost-agency/campaigns/{campaign_id}         — delete campaign
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from api.config import settings
from api.core.deps import CurrentUser, DB, require_module_access, require_usage_budget
from api.models.ghost_agency import LeadProfile, OutreachCampaign, OutreachMessage
from api.schemas.ghost_agency import (
    CampaignCreate,
    CampaignOut,
    GenerateOutreachRequest,
    GenerateOutreachResponse,
    OutreachMessageOut,
)
from api.services.ghost_agency_service import generate_outreach_message
from api.services.usage_service import record_usage

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Generate outreach message ────────────────────────────────────────────────

@router.post("/ghost-agency/generate", response_model=GenerateOutreachResponse, status_code=status.HTTP_201_CREATED)
async def generate_outreach(
    body: GenerateOutreachRequest,
    current_user: CurrentUser,
    db: DB,
    _module_access: Annotated[CurrentUser, Depends(require_module_access("ghost"))],
    _usage_budget: Annotated[tuple[bool, str], Depends(require_usage_budget())],
):
    """Generate a personalized outreach message, save lead profile + message to DB."""
    # Verify campaign belongs to current user
    result = await db.execute(
        select(OutreachCampaign).where(
            OutreachCampaign.id == body.campaign_id,
            OutreachCampaign.user_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    lead_data = body.lead.model_dump()

    # Persist lead profile
    lead_profile = LeadProfile(
        user_id=current_user.id,
        name=lead_data["name"],
        niche=lead_data["niche"],
        platform=lead_data["platform"],
        pain_points=lead_data["pain_points"],
        goals=lead_data["goals"],
        context=lead_data.get("context"),
    )
    db.add(lead_profile)

    # Call AI service
    generated = await generate_outreach_message(
        lead=lead_data,
        campaign_context=body.campaign_context,
        openai_key=settings.OPENAI_API_KEY,
    )

    # Persist outreach message
    outreach_msg = OutreachMessage(
        campaign_id=campaign.id,
        lead_name=lead_data["name"],
        platform=lead_data["platform"],
        message_text=generated["message"],
        hook=generated["hook"],
        personalization_notes=generated["personalization_notes"],
    )
    db.add(outreach_msg)

    campaign.messages_generated += 1

    # Record usage for metering (estimate tokens from generated content length)
    tokens_estimate = max(
        150,
        (len(generated.get("message", "")) + len(generated.get("hook", "")) + len(generated.get("personalization_notes", ""))) // 4,
    )
    await record_usage(current_user.id, "ghost_agency", tokens_estimate, db)

    await db.commit()
    await db.refresh(outreach_msg)

    logger.info(
        f"[ghost_agency] Message generated for lead={lead_data['name']} "
        f"campaign={campaign.id} user={current_user.id}"
    )

    return GenerateOutreachResponse(
        message_id=outreach_msg.id,
        lead_name=outreach_msg.lead_name,
        platform=outreach_msg.platform,
        message_text=outreach_msg.message_text,
        hook=outreach_msg.hook,
        personalization_notes=outreach_msg.personalization_notes,
    )


# ─── Campaigns ────────────────────────────────────────────────────────────────

@router.post("/ghost-agency/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignCreate, current_user: CurrentUser, db: DB):
    """Create a new outreach campaign."""
    campaign = OutreachCampaign(
        user_id=current_user.id,
        name=body.name,
        niche=body.niche,
        target_description=body.target_description,
        status=body.status,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    logger.info(f"[ghost_agency] Campaign created id={campaign.id} user={current_user.id}")
    return campaign


@router.get("/ghost-agency/campaigns", response_model=list[CampaignOut])
async def list_campaigns(current_user: CurrentUser, db: DB):
    """List all campaigns belonging to the authenticated user."""
    result = await db.execute(
        select(OutreachCampaign)
        .where(OutreachCampaign.user_id == current_user.id)
        .order_by(OutreachCampaign.created_at.desc())
    )
    return result.scalars().all()


@router.get("/ghost-agency/campaigns/{campaign_id}/messages", response_model=list[OutreachMessageOut])
async def list_campaign_messages(campaign_id: uuid.UUID, current_user: CurrentUser, db: DB):
    """List all outreach messages for a campaign owned by the authenticated user."""
    # Verify ownership
    result = await db.execute(
        select(OutreachCampaign).where(
            OutreachCampaign.id == campaign_id,
            OutreachCampaign.user_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    msgs_result = await db.execute(
        select(OutreachMessage)
        .where(OutreachMessage.campaign_id == campaign_id)
        .order_by(OutreachMessage.created_at.desc())
    )
    return msgs_result.scalars().all()


@router.delete("/ghost-agency/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: uuid.UUID, current_user: CurrentUser, db: DB):
    """Delete a campaign and all its messages (cascade)."""
    result = await db.execute(
        select(OutreachCampaign).where(
            OutreachCampaign.id == campaign_id,
            OutreachCampaign.user_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    await db.delete(campaign)
    await db.commit()
    logger.info(f"[ghost_agency] Campaign deleted id={campaign_id} user={current_user.id}")
