"""
backend/api/schemas/content_cloner.py — Module 2 Content Cloner schemas (Pydantic v2)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator


class CloneFormats(BaseModel):
    tweet: str
    linkedin: str
    instagram: str
    newsletter: str
    video_script: str


class CloneRequest(BaseModel):
    original_content: str = Field(..., min_length=10, max_length=20_000)
    source_url: str | None = Field(default=None)
    niche: str | None = Field(default=None, max_length=100)


class CloneResponse(BaseModel):
    id: uuid.UUID
    original_content: str
    source_url: str | None
    niche: str | None
    formats: CloneFormats
    created_at: datetime

    model_config = {"from_attributes": True}


class CloneListItem(BaseModel):
    id: uuid.UUID
    niche: str | None
    source_url: str | None
    created_at: datetime
    # Truncated preview of original content
    original_preview: str

    model_config = {"from_attributes": True}


class CloneHistoryResponse(BaseModel):
    items: list[CloneListItem]
    total: int
    limit: int
    offset: int
