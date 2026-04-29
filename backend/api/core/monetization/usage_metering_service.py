"""Central usage metering reads for the Nanovia monetization core."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ._workspace import get_workspace_owner


async def get_usage_snapshot(workspace_id: str, db: AsyncSession) -> dict:
    """Return a workspace-scoped usage snapshot."""
    from api.services.entitlements_service import get_usage_snapshot as legacy_get_usage_snapshot

    owner = await get_workspace_owner(workspace_id, db)
    snapshot = await legacy_get_usage_snapshot(owner, db)
    return {
        **snapshot,
        "workspace_id": str(workspace_id),
        "workspace_mode": "compat_user_owner",
    }


def build_usage_event(
    *,
    workspace_id: str,
    usage_type: str,
    quantity: int,
    actor_id: str | None,
    request_id: str | None,
    idempotency_key: str | None,
    cost: Decimal | int | float = Decimal("0"),
) -> dict:
    """Build the normalized event payload that future usage_events rows will persist."""
    return {
        "type": usage_type,
        "quantity": quantity,
        "cost": str(cost),
        "workspaceId": str(workspace_id),
        "actorId": actor_id,
        "requestId": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": idempotency_key,
    }
