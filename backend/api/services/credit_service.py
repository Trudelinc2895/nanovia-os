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


async def _sync_workspace_credit_projection(user: User, db: AsyncSession) -> None:
    """Keep workspace-native credit_balances aligned with the owner ledger balance."""
    from api.core.monetization._workspace import ensure_owner_workspace

    await ensure_owner_workspace(user, db)


async def _get_authoritative_ledger_balance(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Read the latest balance strictly from the immutable ledger."""
    result = await db.execute(
        select(CreditLedger)
        .where(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.created_at.desc(), CreditLedger.id.desc())
        .limit(1)
    )
    latest_entry = result.scalar_one_or_none()
    return int(latest_entry.balance_after) if latest_entry is not None else 0


async def get_authoritative_credit_balance(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Public read helper for business decisions that need the ledger source of truth."""
    return await _get_authoritative_ledger_balance(user_id, db)


async def _realign_credit_projections(user: User, db: AsyncSession) -> int:
    """
    Restore mutable projections from the ledger before any new mutation.

    `user.credits` and workspace `credit_balances` remain compatibility projections only.
    """
    authoritative_balance = await _get_authoritative_ledger_balance(user.id, db)
    projected_balance = int(user.credits or 0)
    if projected_balance != authoritative_balance:
        logger.critical(
            "[credits] Projection drift detected for user=%s user.credits=%s ledger=%s",
            user.id,
            projected_balance,
            authoritative_balance,
        )
        user.credits = authoritative_balance

    await _sync_workspace_credit_projection(user, db)
    return authoritative_balance


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
    if not idempotency_key:
        logger.warning("[credits] add_credits missing idempotency_key for user=%s source=%s", user_id, source)

    if idempotency_key:
        # Check idempotency BEFORE acquiring lock to avoid unnecessary locking
        result = await db.execute(
            select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("[credits] Idempotent duplicate key=%s — skipping", idempotency_key)
            return existing

    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"add_credits: user {user_id} not found")

    try:
        current_balance = await _realign_credit_projections(user, db)
        next_balance = current_balance + amount
        user.credits = next_balance
        entry = CreditLedger(
            user_id=user_id,
            type="purchase",
            amount=amount,
            balance_after=next_balance,
            source=source,
            idempotency_key=idempotency_key,
            note=note,
        )
        db.add(user)
        db.add(entry)
        await _sync_workspace_credit_projection(user, db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
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
    idempotency_key: str | None = None,
) -> bool:
    """Deduct credits and record in ledger. Returns False if insufficient balance.
    Idempotent when idempotency_key is provided (safe to replay from webhooks)."""
    if not idempotency_key:
        logger.warning("[credits] deduct_credits missing idempotency_key for user=%s source=%s", getattr(user, "id", None), source)
    if idempotency_key:
        result = await db.execute(
            select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key)
        )
        if result.scalar_one_or_none():
            return True  # already processed

    # Re-fetch with row lock to prevent concurrent double-deduction.
    # The user param may be stale (fetched earlier in the request lifecycle).
    locked = await db.execute(select(User).where(User.id == user.id).with_for_update())
    user = locked.scalar_one_or_none()
    if not user:
        return False

    current_balance = await _realign_credit_projections(user, db)
    if current_balance < amount:
        return False

    try:
        next_balance = current_balance - amount
        user.credits = next_balance
        entry = CreditLedger(
            user_id=user.id,
            type="deduction",
            amount=-amount,
            balance_after=next_balance,
            source=source,
            idempotency_key=idempotency_key,
            note=note,
        )
        db.add(user)
        db.add(entry)
        await _sync_workspace_credit_projection(user, db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info("[credits] -%d for user=%s balance=%d source=%s", amount, user.id, user.credits, source)
    if _HAS_PROM:
        _kt_credits_deducted.labels(reason=source).inc(amount)

    # ── Low-credit alert: fire once when balance crosses below threshold ───────
    _LOW_CREDIT_THRESHOLD = 3
    if current_balance >= _LOW_CREDIT_THRESHOLD > next_balance:
        import asyncio as _asyncio
        try:
            from api.services.email_service import send_low_credits
            _asyncio.create_task(
                send_low_credits(user.email, getattr(user, "full_name", None) or "", next_balance)
            )
        except Exception as _exc:
            logger.warning("[credits] Could not queue low-credit alert for user=%s: %s", user.id, _exc)

    return True


async def adjust_credits(
    user_id: uuid.UUID,
    amount: int,
    source: str,
    db: AsyncSession,
    note: str | None = None,
    idempotency_key: str | None = None,
) -> CreditLedger:
    """Admin-initiated adjustment. amount can be positive or negative."""
    if not idempotency_key:
        logger.warning("[credits] adjust_credits missing idempotency_key for user=%s source=%s", user_id, source)
    if idempotency_key:
        result = await db.execute(
            select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("[credits] Idempotent adjust key=%s — skipping", idempotency_key)
            return existing

    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"adjust_credits: user {user_id} not found")

    try:
        current_balance = await _realign_credit_projections(user, db)
        next_balance = max(0, current_balance + amount)
        user.credits = next_balance
        entry = CreditLedger(
            user_id=user_id,
            type="adjustment",
            amount=amount,
            balance_after=next_balance,
            source=source,
            idempotency_key=idempotency_key,
            note=note,
        )
        db.add(user)
        db.add(entry)
        await _sync_workspace_credit_projection(user, db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
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
