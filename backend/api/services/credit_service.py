"""backend/api/services/credit_service.py — Credit balance management with ledger.

All credit mutations must go through this service.
Direct writes to user.credits are forbidden — use these functions instead.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.credit_ledger import CreditLedger
from api.models.user import User

logger = logging.getLogger(__name__)

# ── Prometheus counter (graceful fallback if not installed) ───────────────────
try:
    from prometheus_client import Counter
    _kt_credits_deducted = Counter(
        "kt_credits_deducted_total",
        "Overage credits deducted from user balance",
        ["reason"],
    )
    _kt_credits_added = Counter(
        "kt_credits_added_total",
        "Credits added to user balance",
        ["source"],
    )
    _HAS_PROM = True
except Exception:
    _HAS_PROM = False


async def add_credits(
    user_id: uuid.UUID,
    amount: int,
    source: str,
    db: AsyncSession,
    idempotency_key: str | None = None,
    note: str | None = None,
) -> CreditLedger:
    """Add credits and record in ledger. Idempotent when idempotency_key is provided."""
    if amount <= 0:
        raise ValueError(f"add_credits: amount must be positive, got {amount}")

    if idempotency_key:
        result = await db.execute(
            select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("[credits] Idempotent duplicate key=%s — skipping", idempotency_key)
            return existing

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"add_credits: user {user_id} not found")

    user.credits = (user.credits or 0) + amount
    entry = CreditLedger(
        user_id=user_id,
        type="purchase",
        amount=amount,
        balance_after=user.credits,
        source=source,
        idempotency_key=idempotency_key,
        note=note,
    )
    db.add(user)
    db.add(entry)
    await db.commit()
    logger.info("[credits] +%d for user=%s balance=%d source=%s", amount, user_id, user.credits, source)
    if _HAS_PROM:
        _kt_credits_added.labels(source=source).inc(amount)
    return entry


async def deduct_credits(
    user: User,
    source: str,
    db: AsyncSession,
    amount: int = 1,
    note: str | None = None,
) -> bool:
    """Deduct credits and record in ledger. Returns False if insufficient balance."""
    if (user.credits or 0) < amount:
        return False

    user.credits -= amount
    entry = CreditLedger(
        user_id=user.id,
        type="deduction",
        amount=-amount,
        balance_after=user.credits,
        source=source,
        note=note,
    )
    db.add(user)
    db.add(entry)
    await db.commit()
    logger.info("[credits] -%d for user=%s balance=%d source=%s", amount, user.id, user.credits, source)
    if _HAS_PROM:
        _kt_credits_deducted.labels(reason=source).inc(amount)
    return True


async def adjust_credits(
    user_id: uuid.UUID,
    amount: int,
    source: str,
    db: AsyncSession,
    note: str | None = None,
) -> CreditLedger:
    """Admin-initiated adjustment. amount can be positive or negative."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"adjust_credits: user {user_id} not found")

    user.credits = max(0, (user.credits or 0) + amount)
    entry = CreditLedger(
        user_id=user_id,
        type="adjustment",
        amount=amount,
        balance_after=user.credits,
        source=source,
        note=note,
    )
    db.add(user)
    db.add(entry)
    await db.commit()
    logger.info("[credits] adjust %+d for user=%s balance=%d", amount, user_id, user.credits)
    return entry


async def get_history(
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 50,
) -> list[dict]:
    """Return ledger history for a user, newest first."""
    result = await db.execute(
        select(CreditLedger)
        .where(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": str(e.id),
            "type": e.type,
            "amount": e.amount,
            "balance_after": e.balance_after,
            "source": e.source,
            "note": e.note,
            "created_at": e.created_at.isoformat(),
        }
        for e in result.scalars().all()
    ]
