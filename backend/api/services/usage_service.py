"""
backend/api/services/usage_service.py
Usage tracking and plan-limit enforcement for metered AI consumption.

GPT-4o-mini pricing: $0.000002 per token (~$0.002 / 1K tokens).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models.usage_record import UsageRecord

# Cost per token in USD (gpt-4o-mini blended rate)
_COST_PER_TOKEN = Decimal("0.000002")

# Message limits per plan. -1 = unlimited.
_PLAN_LIMITS: dict[str, int] = {
    "free": 50,
    "starter": 500,
    "pro": 5000,
    "business": -1,
}

_redis_pool: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
    return _redis_pool


def _month_key(user_id: uuid.UUID) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"usage:{user_id}:{month}"


async def record_usage(
    user_id: uuid.UUID,
    module: str,
    tokens_used: int,
    db: AsyncSession,
) -> UsageRecord:
    """
    Persist a usage record and increment the Redis monthly counter.
    Returns the saved UsageRecord.
    """
    cost = _COST_PER_TOKEN * tokens_used
    record = UsageRecord(
        user_id=user_id,
        module=module,
        tokens_used=max(tokens_used, 0),
        cost_usd=cost,
    )
    db.add(record)
    await db.flush()

    # Increment Redis counter for fast limit checks (fire-and-forget; fail open)
    try:
        redis = await _get_redis()
        key = _month_key(user_id)
        count = await redis.incr(key)
        if count == 1:
            # Set TTL: expire after ~35 days to auto-clean old keys
            await redis.expire(key, 35 * 24 * 3600)
    except Exception:
        pass

    return record


async def get_monthly_usage(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """
    Return usage stats for the current calendar month.
    Message count from Redis (fast), token/cost totals from DB.
    """
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    month_start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)

    # Redis counter for message count
    messages_count = 0
    try:
        redis = await _get_redis()
        raw = await redis.get(_month_key(user_id))
        messages_count = int(raw) if raw else 0
    except Exception:
        pass

    # DB aggregates for token and cost totals
    result = await db.execute(
        select(
            func.coalesce(func.sum(UsageRecord.tokens_used), 0).label("tokens_total"),
            func.coalesce(func.sum(UsageRecord.cost_usd), Decimal("0")).label("cost_total"),
            func.count(UsageRecord.id).label("db_count"),
        ).where(
            UsageRecord.user_id == user_id,
            UsageRecord.created_at >= month_start,
        )
    )
    row = result.one()

    # Prefer DB count as ground truth if Redis is out of sync
    if messages_count == 0 and row.db_count > 0:
        messages_count = row.db_count

    return {
        "month": month,
        "messages_count": messages_count,
        "tokens_total": int(row.tokens_total),
        "cost_usd_total": float(row.cost_total),
    }


async def check_usage_limit(
    user_id: uuid.UUID,
    plan: str,
    db: AsyncSession,  # noqa: ARG001 — reserved for DB-backed fallback
) -> bool:
    """
    Return True if the user is within their monthly message limit.
    Returns True (fail open) if Redis is unavailable.
    -1 limit means unlimited (business plan).
    """
    limit = _PLAN_LIMITS.get(plan, _PLAN_LIMITS["free"])
    if limit == -1:
        return True

    try:
        redis = await _get_redis()
        raw = await redis.get(_month_key(user_id))
        count = int(raw) if raw else 0
        return count < limit
    except Exception:
        # Redis unavailable — fail open to avoid blocking users
        return True
