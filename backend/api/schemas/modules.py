"""
backend/api/schemas/modules.py — Module 1 AI Operator schemas
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(min_length=1, max_length=32_000)


class OperatorChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)
    conversation_id: uuid.UUID | None = None
    context: str | None = Field(
        default=None,
        description="Optional additional context (emails, docs, etc.)",
        max_length=16_000,
    )


class OperatorChatResponse(BaseModel):
    conversation_id: uuid.UUID
    reply: str
    model_used: str
    token_count: int
    messages: list[ChatMessage]


class ConversationSummary(BaseModel):
    id: uuid.UUID
    module: str
    title: str | None
    token_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
