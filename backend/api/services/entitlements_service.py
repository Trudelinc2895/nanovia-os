"""
backend/api/services/entitlements_service.py
Centralized entitlements service — thin wrapper over billing_service + usage_service.

This module provides a clean, unified API for:
  - Reading the active plan for a user
  - Computing full entitlements (plan limits + feature flags + subscription status)
  - Checking individual feature access
  - Querying remaining quota per usage type
  - Getting a rich usage snapshot (dashboard, alerting)

RULES:
  - Does NOT duplicate pricing/plan logic — delegates to billing_service.PLANS_CONFIG
  - Does NOT write any state — read-only service
  - All DB reads are efficient (single queries)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user_module import UserModule
from api.models.user import User
from api.services.module_registry import canonicalize_module_slug, get_module_lookup_slugs


# ─── Plan helpers ─────────────────────────────────────────────────────────────

def get_active_plan(user: User) -> str:
    """
    Return the user's active plan key.
    Always returns a valid key from PLANS_CONFIG (free / pro / business).
    """
    from api.services.billing_service import PLANS_CONFIG
    plan = getattr(user, "plan", "free") or "free"
    return plan if plan in PLANS_CONFIG else "free"


async def get_entitlements(user: User, db: AsyncSession) -> dict[str, Any]:
    """
    Compute full entitlements for a user, including live usage stats.

    Delegates core logic to billing_service.compute_entitlements().
    Enriches the result with live monthly usage from usage_service.

    Returns the same structure as compute_entitlements() with an added
    "usage" key containing the current month's consumption.
    """
    from api.services.billing_service import (
        compute_entitlements,
        get_active_subscription,
    )
    from api.services.credit_service import get_authoritative_credit_balance
    from api.services.usage_service import get_monthly_usage

    sub = await get_active_subscription(user.id, db)
    usage = await get_monthly_usage(user.id, db)

    entitlements = compute_entitlements(user, sub, usage)
    entitlements["credits"] = await get_authoritative_credit_balance(user.id, db)
    entitlements["usage"] = usage
    return entitlements


async def get_effective_plan(user: User, db: AsyncSession) -> str:
    """Return the effective plan after subscription-state degradation is applied."""
    entitlements = await get_entitlements(user, db)
    return str(entitlements["plan"])


def can_use_feature(user: User, feature: str) -> bool:
    """
    Return True if the user's plan enables the given feature flag.
    Server-side only — never trust client-side claims.

    Delegates to billing_service.has_feature().
    """
    from api.services.billing_service import has_feature
    plan = get_active_plan(user)
    return has_feature(plan, feature)


async def can_access_feature(user: User, feature: str, db: AsyncSession) -> bool:
    """Return True when the effective entitlements enable the feature."""
    entitlements = await get_entitlements(user, db)
    return bool(entitlements["features_enabled"].get(feature, False))


async def has_module_access(user: User, module_slug: str, db: AsyncSession) -> bool:
    """
    Return True if the user can access a module via plan inclusion or active
    à-la-carte purchase.
    """
    from api.services.billing_service import MODULES_CONFIG

    canonical_slug = canonicalize_module_slug(module_slug)
    if not canonical_slug:
        return False

    module_cfg = MODULES_CONFIG.get(canonical_slug)
    if not module_cfg:
        return False

    effective_plan = await get_effective_plan(user, db)
    if effective_plan in module_cfg.get("included_in_plans", []):
        return True

    lookup_slugs = get_module_lookup_slugs(canonical_slug)
    result = await db.execute(
        select(UserModule).where(
            UserModule.user_id == user.id,
            UserModule.module_slug.in_(lookup_slugs),
        )
    )
    module_access = result.scalar_one_or_none()
    return bool(module_access and module_access.is_active())


async def get_remaining_quota(
    user: User,
    db: AsyncSession,
    usage_type: str = "ai_messages_per_month",
) -> dict[str, Any]:
    """
    Return remaining quota for a given metered resource.

    Args:
        user: ORM User instance
        db: async session
        usage_type: limit key from PLANS_CONFIG["limits"]
                    (e.g. "ai_messages_per_month", "api_calls_per_day")

    Returns:
        {
            "limit": int,          # -1 = unlimited
            "used": int,
            "remaining": int,      # -1 = unlimited
            "pct_used": float,     # 0.0–100.0
            "exceeded": bool,
        }
    """
    from api.services.billing_service import PLANS_CONFIG
    from api.services.usage_service import get_monthly_usage

    plan = get_active_plan(user)
    plan_cfg = PLANS_CONFIG.get(plan, PLANS_CONFIG["free"])
    limit: int = plan_cfg["limits"].get(usage_type, 0)

    if usage_type == "ai_messages_per_month":
        usage_data = await get_monthly_usage(user.id, db)
        used = usage_data["messages_count"]
    else:
        # For future usage types (api_calls_per_day, storage_gb, etc.)
        # add specific queries here. Default: unknown → 0 used.
        used = 0

    if limit == -1:
        return {
            "limit": -1,
            "used": used,
            "remaining": -1,
            "pct_used": 0.0,
            "exceeded": False,
        }

    remaining = max(0, limit - used)
    pct_used = min(100.0, round((used / limit) * 100, 1)) if limit > 0 else 0.0
    exceeded = used >= limit

    return {
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "pct_used": pct_used,
        "exceeded": exceeded,
    }


async def get_usage_snapshot(user: User, db: AsyncSession) -> dict[str, Any]:
    """
    Rich usage snapshot combining entitlements, per-module breakdown,
    credit balance, and quota state for all metered resources.

    Designed for: dashboard usage page, admin user detail, alerting triggers.

    Returns:
        {
            "plan": str,
            "status": str,
            "credits": int,
            "quota": {
                "ai_messages": {...},   # get_remaining_quota() structure
            },
            "usage_this_month": {...},  # get_monthly_usage() structure
            "module_breakdown": [...],  # per-module usage list
            "features_enabled": {...},
            "subscription": {...},
            "snapshot_at": str,         # ISO UTC timestamp
        }
    """
    from api.services.billing_service import (
        compute_entitlements,
        get_active_subscription,
    )
    from api.services.credit_service import get_authoritative_credit_balance
    from api.services.usage_service import get_monthly_usage, get_module_breakdown

    # Parallel-friendly: run sub + usage queries together
    sub = await get_active_subscription(user.id, db)
    usage_month = await get_monthly_usage(user.id, db)
    breakdown = await get_module_breakdown(user.id, db, days=30)

    entitlements = compute_entitlements(user, sub, usage_month)
    authoritative_credits = await get_authoritative_credit_balance(user.id, db)
    quota_ai = await get_remaining_quota(user, db, "ai_messages_per_month")

    return {
        "plan": entitlements["plan"],
        "status": entitlements["status"],
        "credits": authoritative_credits,
        "quota": {
            "ai_messages": quota_ai,
        },
        "usage_this_month": usage_month,
        "module_breakdown": breakdown,
        "features_enabled": entitlements["features_enabled"],
        "subscription": entitlements["subscription"],
        "upsell": entitlements.get("upsell"),
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }
