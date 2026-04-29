"""
backend/api/routers/analytics.py — Usage analytics & gamification

  GET  /analytics/history   — usage history (last N days) — requires advanced_analytics
  GET  /analytics/breakdown — module breakdown chart data
  GET  /analytics/export    — CSV export — requires data_export feature
  GET  /analytics/milestones — gamification progression
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.core.deps import CurrentUser, DB, require_feature
from api.schemas.billing import (
    MilestoneStatus,
    MilestonesResponse,
    ModuleBreakdownItem,
    UsageHistoryItem,
    UsageHistoryResponse,
)
from api.services.billing_service import MILESTONES
from api.services.entitlements_service import get_entitlements
from api.services.usage_service import (
    get_module_breakdown,
    get_monthly_usage,
    get_usage_history,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/analytics/history", response_model=UsageHistoryResponse)
async def usage_history(
    current_user: CurrentUser,
    db: DB,
    _: Annotated[CurrentUser, Depends(require_feature("advanced_analytics"))],
    days: int = Query(default=30, ge=1, le=90, description="Look-back window in days"),
):
    """
    Return detailed usage history for the authenticated user.
    Requires advanced_analytics feature (pro+).
    Data lock-in: the richer the history, the more valuable the account.
    """
    records_raw = await get_usage_history(current_user.id, db, days=days)
    breakdown_raw = await get_module_breakdown(current_user.id, db, days=days)

    records = [UsageHistoryItem(**r) for r in records_raw]
    breakdown = [ModuleBreakdownItem(**b) for b in breakdown_raw]

    total_messages = sum(b.message_count for b in breakdown)
    total_tokens = sum(b.tokens_total for b in breakdown)
    total_cost = round(sum(b.cost_usd_total for b in breakdown), 6)

    return UsageHistoryResponse(
        days=days,
        records=records,
        breakdown=breakdown,
        total_messages=total_messages,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
    )


@router.get("/analytics/breakdown")
async def module_breakdown(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(default=30, ge=1, le=90),
):
    """Module-level usage breakdown. Available on all plans (free only sees last 7 days)."""
    entitlements = await get_entitlements(current_user, db)
    effective_days = days if entitlements["features_enabled"].get("advanced_analytics", False) else min(days, 7)
    breakdown = await get_module_breakdown(current_user.id, db, days=effective_days)
    return {"days": effective_days, "breakdown": breakdown}


@router.get("/analytics/export")
async def export_usage_csv(
    current_user: CurrentUser,
    db: DB,
    _: Annotated[CurrentUser, Depends(require_feature("data_export"))],
    days: int = Query(default=30, ge=1, le=365),
):
    """
    Export usage records as CSV. Requires data_export feature (pro+).
    This is a data lock-in feature: users with rich history are less likely to churn.
    """
    records = await get_usage_history(current_user.id, db, days=days, limit=5000)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "module", "tokens_used", "cost_usd", "created_at"])
    writer.writeheader()
    writer.writerows(records)
    output.seek(0)

    filename = f"kt-usage-{current_user.id}-last{days}d.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/analytics/milestones", response_model=MilestonesResponse)
async def user_milestones(current_user: CurrentUser, db: DB):
    """
    Return gamification milestones for the authenticated user.
    Drives progression, engagement, and upgrade motivation.
    """
    entitlements = await get_entitlements(current_user, db)
    usage = await get_monthly_usage(current_user.id, db)
    total_messages = usage.get("messages_count", 0)

    # Lifetime count (all records, not just this month)
    from sqlalchemy import func, select
    from api.models.usage_record import UsageRecord
    result = await db.execute(
        select(func.count(UsageRecord.id)).where(UsageRecord.user_id == current_user.id)
    )
    lifetime_messages: int = result.scalar_one() or 0

    statuses: list[MilestoneStatus] = []
    for m in MILESTONES:
        # Plan-based milestones
        if "plan" in m:
            plan = entitlements["plan"]
            unlocked = plan in ("business",) if m["plan"] == "business" else plan in ("pro", "business")
        else:
            unlocked = lifetime_messages >= m["threshold"]

        statuses.append(MilestoneStatus(
            key=m["key"],
            label=m["label"],
            icon=m["icon"],
            unlocked=unlocked,
        ))

    total_unlocked = sum(1 for s in statuses if s.unlocked)
    progress_pct = round(total_unlocked / len(statuses) * 100, 1) if statuses else 0.0

    return MilestonesResponse(
        milestones=statuses,
        total_unlocked=total_unlocked,
        total=len(statuses),
        progress_pct=progress_pct,
    )
