"""Central billing orchestration wrappers for the Nanovia monetization core."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ._workspace import get_workspace_owner


async def get_active_plan(workspace_id: str, db: AsyncSession) -> str:
    """Return the effective active plan for a workspace."""
    from api.services.entitlements_service import get_effective_plan as legacy_get_effective_plan

    owner = await get_workspace_owner(workspace_id, db)
    return await legacy_get_effective_plan(owner, db)


async def resolve_overage_policy(workspace_id: str, db: AsyncSession) -> dict:
    """Resolve how Nanovia should behave once quota is exhausted."""
    from .entitlements_service import get_entitlements

    entitlements = await get_entitlements(workspace_id, db)
    overage_allowed = bool(entitlements["features_enabled"].get("overage_allowed", False))
    credits_remaining = int(entitlements.get("credits", 0) or 0)

    action = "block"
    if overage_allowed and credits_remaining > 0:
        action = "deduct_credits"
    elif overage_allowed:
        action = "block_no_credits"

    return {
        "workspace_id": str(workspace_id),
        "plan": entitlements["plan"],
        "overage_allowed": overage_allowed,
        "credits_remaining": credits_remaining,
        "action": action,
    }
