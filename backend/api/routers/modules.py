"""
backend/api/routers/modules.py — Module 1: AI Personal Operator
POST /api/v1/modules/operator/chat    — send message, get AI reply
GET  /api/v1/modules/operator/history — list conversations
GET  /api/v1/modules/operator/{id}    — get conversation
DELETE /api/v1/modules/operator/{id}  — delete conversation
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from api.config import settings
from api.core.deps import CurrentUser, DB
from api.models.conversation import Conversation
from api.schemas.modules import (
    ConversationSummary,
    OperatorChatRequest,
    OperatorChatResponse,
    ChatMessage,
)
from api.services.usage_service import check_and_charge_usage, record_usage

router = APIRouter()

# ── System prompt for AI Personal Operator ────────────────────────────────────
OPERATOR_SYSTEM_PROMPT = """You are an elite AI Personal Operator — a highly capable executive assistant.

Your role:
- Help with emails, decisions, strategy, task prioritization, and business clarity
- Give precise, actionable answers — never vague
- Think like a senior business advisor + chief of staff
- When asked to draft something (email, message, document), produce the full draft immediately
- When asked for a decision, analyze pros/cons and give a clear recommendation
- Remember the full context of this conversation

Communication style:
- Direct, clear, professional
- Structured when helpful (use lists/bullets for complex info)
- Never add filler phrases or unnecessary preamble
- Get straight to the value"""

# ── AI provider abstraction (OpenAI with Ollama fallback) ─────────────────────

async def _call_ai(messages: list[dict], model: str = "gpt-4o-mini") -> tuple[str, int]:
    """Returns (reply_content, token_count). Tries OpenAI first, falls back to orchestrator."""

    # Try OpenAI if key is set
    if settings.OPENAI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 2048,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                reply = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("total_tokens", len(reply) // 4)
                return reply, tokens
        except Exception as e:
            # Log and fall through to orchestrator
            print(f"[OpenAI error] {e} — falling back to orchestrator")

    # Fallback: internal AI orchestrator (Ollama)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "http://ai-orchestrator:8020/chat",
                json={"messages": messages, "model": settings.OLLAMA_DEFAULT_MODEL},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("reply", "")
            tokens = data.get("token_count", len(reply) // 4)
            return reply, tokens
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"AI service unavailable: {e}",
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/operator/chat", response_model=OperatorChatResponse)
async def operator_chat(body: OperatorChatRequest, current_user: CurrentUser, db: DB):
    """Send a message to the AI Personal Operator. Maintains conversation history."""

    # Enforce plan usage quota before any AI call (overage → credit deduction)
    allowed, reason = await check_and_charge_usage(current_user, db)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Limite mensuelle atteinte. Upgrade ton plan pour continuer.",
        )

    # Load or create conversation
    conv: Conversation | None = None
    if body.conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == body.conversation_id,
                Conversation.user_id == current_user.id,
                Conversation.module == "operator",
            )
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

    if not conv:
        conv = Conversation(user_id=current_user.id, module="operator", messages=[])
        db.add(conv)
        await db.flush()

    # Build message list for API call
    api_messages = [{"role": "system", "content": OPERATOR_SYSTEM_PROMPT}]

    if body.context:
        api_messages.append({
            "role": "system",
            "content": f"Additional context provided by user:\n{body.context}",
        })

    # Include previous conversation history (last 20 messages to manage context window)
    history = conv.messages[-20:] if len(conv.messages) > 20 else conv.messages
    for msg in history:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    api_messages.append({"role": "user", "content": body.message})

    # Call AI
    reply, tokens = await _call_ai(api_messages)

    # Persist new messages
    now_iso = datetime.now(timezone.utc).isoformat()
    new_messages = list(conv.messages) + [
        {"role": "user", "content": body.message, "ts": now_iso},
        {"role": "assistant", "content": reply, "ts": now_iso},
    ]
    conv.messages = new_messages
    conv.token_count = conv.token_count + tokens
    conv.model_used = "gpt-4o-mini" if settings.OPENAI_API_KEY else settings.OLLAMA_DEFAULT_MODEL

    # Auto-title from first user message
    if not conv.title and body.message:
        conv.title = body.message[:80] + ("…" if len(body.message) > 80 else "")

    await db.flush()
    await record_usage(current_user.id, "operator", tokens, db)

    return OperatorChatResponse(
        conversation_id=conv.id,
        reply=reply,
        model_used=conv.model_used or "unknown",
        token_count=conv.token_count,
        messages=[ChatMessage(role=m["role"], content=m["content"]) for m in conv.messages],
    )


@router.get("/operator/history", response_model=list[ConversationSummary])
async def operator_history(current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id, Conversation.module == "operator")
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    return [ConversationSummary.model_validate(c) for c in result.scalars()]


@router.get("/operator/{conversation_id}", response_model=OperatorChatResponse)
async def get_conversation(conversation_id: uuid.UUID, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return OperatorChatResponse(
        conversation_id=conv.id,
        reply="",
        model_used=conv.model_used or "unknown",
        token_count=conv.token_count,
        messages=[ChatMessage(role=m["role"], content=m["content"]) for m in conv.messages],
    )


@router.delete("/operator/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)

