"""Central entitlement reads for the Nanovia monetization core."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ._workspace import get_workspace, get_workspace_owner, workspace_is_active

_METERED_FEATURE_QUOTAS: dict[str, str] = {
    "automation": "ai_messages",
}


async def get_entitlements(workspace_id: str, db: AsyncSession) -> dict:
    """Return the computed workspace entitlements."""
    from api.services.entitlements_service import get_entitlements as legacy_get_entitlements

    owner = await get_workspace_owner(workspace_id, db)
    entitlements = await legacy_get_entitlements(owner, db)
    return {
        **entitlements,
        "workspace_id": str(workspace_id),
        "workspace_mode": "compat_user_owner",
    }


async def can_use_feature(workspace_id: str, feature: str, db: AsyncSession) -> bool:
    workspace = await get_workspace(workspace_id, db)
    if workspace is None or not workspace_is_active(workspace):
        return False

    entitlements = await get_entitlements(workspace_id, db)
    if entitlements.get("status") not in {"active"}:
        return False
    if not bool(entitlements["features_enabled"].get(feature, False)):
        return False

    quota_key = _METERED_FEATURE_QUOTAS.get(feature)
    if quota_key is None:
        return True

    from .billing_service import resolve_overage_policy
    from .usage_metering_service import get_usage_snapshot

    snapshot = await get_usage_snapshot(workspace_id, db)
    quota_state = snapshot.get("quota", {}).get(quota_key, {})
    if not quota_state.get("exceeded", False):
        return True

    policy = await resolve_overage_policy(workspace_id, db)
    return policy["action"] == "deduct_credits"
