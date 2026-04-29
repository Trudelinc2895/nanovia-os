"""Nanovia centralized monetization core.

This package is the single entry point for monetization reads and writes.
During the workspace migration, ``workspaceId`` is temporarily mapped to the
workspace owner's user id for backward compatibility with the current schema.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .billing_service import get_active_plan, resolve_overage_policy
from .credits_service import consume_credits
from .entitlements_service import can_use_feature, get_entitlements
from .usage_metering_service import get_usage_snapshot


async def getActivePlan(workspaceId: str, db: AsyncSession) -> str:
    return await get_active_plan(workspaceId, db)


async def getEntitlements(workspaceId: str, db: AsyncSession) -> dict:
    return await get_entitlements(workspaceId, db)


async def canUseFeature(workspaceId: str, feature: str, db: AsyncSession) -> bool:
    return await can_use_feature(workspaceId, feature, db)


async def consumeCredits(
    workspaceId: str,
    usageType: str,
    quantity: int,
    db: AsyncSession,
    *,
    actorId: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    return await consume_credits(
        workspaceId,
        usageType,
        quantity,
        db,
        actor_id=actorId,
        idempotency_key=idempotency_key,
    )


async def getUsageSnapshot(workspaceId: str, db: AsyncSession) -> dict:
    return await get_usage_snapshot(workspaceId, db)


async def resolveOveragePolicy(workspaceId: str, db: AsyncSession) -> dict:
    return await resolve_overage_policy(workspaceId, db)


__all__ = [
    "canUseFeature",
    "consumeCredits",
    "getActivePlan",
    "getEntitlements",
    "getUsageSnapshot",
    "resolveOveragePolicy",
]
