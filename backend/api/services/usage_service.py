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

# Message limits per plan. -1 = unlimited. Must match PLANS_CONFIG in billing_service.
_PLAN_LIMITS: dict[str, int] = {
    "free": 50,
    "pro": 1000,
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


async def check_and_charge_usage(user: object, db: AsyncSession) -> tuple[bool, str]:
    """
    Full usage gate with overage credit fallback.

    Returns (allowed: bool, reason: str):
      "within_limit"     — under plan quota, proceed normally
      "unlimited"        — business plan, no cap
      "credit_deducted"  — over quota but 1 credit was deducted (overage billing)
      "limit_exceeded"   — over quota, no credits or overage not enabled
      "redis_unavailable"— Redis down, fail-open

    Overage logic (revenue expansion):
      When a user exceeds their monthly limit AND their plan has overage_allowed=True
      AND they have at least 1 credit, 1 credit is atomically deducted instead of
      blocking the request. Each credit = 1 overage message.
    """
    from api.services.billing_service import has_feature  # avoid circular import

    plan: str = getattr(user, "plan", "free")
    user_id: uuid.UUID = getattr(user, "id")
    limit = _PLAN_LIMITS.get(plan, _PLAN_LIMITS["free"])

    if limit == -1:
        return True, "unlimited"

    try:
        redis = await _get_redis()
        raw = await redis.get(_month_key(user_id))
        count = int(raw) if raw else 0
    except Exception:
        return True, "redis_unavailable"

    if count < limit:
        return True, "within_limit"

    # Over limit — attempt overage credit deduction
    if has_feature(plan, "overage_allowed") and (getattr(user, "credits", 0) or 0) > 0:
        user.credits -= 1  # type: ignore[attr-defined]
        db.add(user)
        await db.commit()
        return True, "credit_deducted"

    return False, "limit_exceeded"


async def get_usage_history(
    user_id: uuid.UUID,
    db: AsyncSession,
    days: int = 30,
    limit: int = 200,
) -> list[dict]:
    """
    Return per-record usage history for the last N days.
    Used by analytics dashboard (data lock-in feature).
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(UsageRecord)
        .where(UsageRecord.user_id == user_id, UsageRecord.created_at >= cutoff)
        .order_by(UsageRecord.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "module": r.module,
            "tokens_used": r.tokens_used,
            "cost_usd": float(r.cost_usd),
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]


async def get_module_breakdown(user_id: uuid.UUID, db: AsyncSession, days: int = 30) -> list[dict]:
    """
    Return usage grouped by module for the last N days.
    Powers the analytics pie chart.
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            UsageRecord.module,
            func.count(UsageRecord.id).label("message_count"),
            func.coalesce(func.sum(UsageRecord.tokens_used), 0).label("tokens_total"),
            func.coalesce(func.sum(UsageRecord.cost_usd), Decimal("0")).label("cost_total"),
        )
        .where(UsageRecord.user_id == user_id, UsageRecord.created_at >= cutoff)
        .group_by(UsageRecord.module)
        .order_by(func.count(UsageRecord.id).desc())
    )
    rows = result.all()
    return [
        {
            "module": r.module,
            "message_count": r.message_count,
            "tokens_total": int(r.tokens_total),
            "cost_usd_total": float(r.cost_total),
        }
        for r in rows
    ]
