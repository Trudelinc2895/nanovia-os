"""
backend/api/schemas/ghost_agency.py — Module 4 Ghost Agency schemas
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ─── Lead Profile ─────────────────────────────────────────────────────────────

class LeadProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    niche: str = Field(..., min_length=1, max_length=255)
    platform: str = Field(..., pattern="^(linkedin|instagram|twitter|email)$")
    pain_points: str = Field(..., min_length=1)
    goals: str = Field(..., min_length=1)
    context: str | None = None


class LeadProfileOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    niche: str
    platform: str
    pain_points: str
    goals: str
    context: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Outreach Campaign ────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    niche: str = Field(..., min_length=1, max_length=255)
    target_description: str = Field(..., min_length=1)
    status: str = Field(default="draft", pattern="^(draft|active|paused)$")


class CampaignOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    niche: str
    target_description: str
    messages_generated: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Outreach Message ─────────────────────────────────────────────────────────

class OutreachMessageOut(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    lead_name: str
    platform: str
    message_text: str
    hook: str
    personalization_notes: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Generate request/response ────────────────────────────────────────────────

class GenerateOutreachRequest(BaseModel):
    lead: LeadProfileCreate
    campaign_id: uuid.UUID
    campaign_context: str = Field(default="", max_length=1000)


class GenerateOutreachResponse(BaseModel):
    message_id: uuid.UUID
    lead_name: str
    platform: str
    message_text: str
    hook: str
    personalization_notes: str
