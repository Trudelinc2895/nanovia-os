"""Central credit consumption for the Nanovia monetization core."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from api.services.credit_service import deduct_credits

from ._workspace import get_workspace, get_workspace_owner, workspace_is_active


async def consume_credits(
    workspace_id: str,
    usage_type: str,
    quantity: int,
    db: AsyncSession,
    *,
    actor_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Deduct credits from a workspace in a single centralized call."""
    if quantity <= 0:
        raise ValueError("quantity must be greater than zero")

    workspace = await get_workspace(workspace_id, db)
    if workspace is None or not workspace_is_active(workspace):
        return {
            "workspace_id": str(workspace_id),
            "usage_type": usage_type,
            "quantity": quantity,
            "allowed": False,
            "balance_after": 0,
            "reason": "workspace_inactive",
        }

    owner = await get_workspace_owner(workspace_id, db)
    note = f"workspace={workspace_id} usage_type={usage_type}"
    if actor_id:
        note += f" actor={actor_id}"

    allowed = await deduct_credits(
        owner,
        source=f"workspace:{usage_type}",
        db=db,
        amount=quantity,
        note=note,
        idempotency_key=idempotency_key,
    )
    refreshed_owner = await get_workspace_owner(workspace_id, db)
    return {
        "workspace_id": str(workspace_id),
        "usage_type": usage_type,
        "quantity": quantity,
        "allowed": allowed,
        "balance_after": int(refreshed_owner.credits or 0),
        "reason": "credits_consumed" if allowed else "insufficient_credits",
    }
