"""Central Stripe webhook handling for the Nanovia monetization core."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.services.billing_service import (
    claim_webhook_event,
    get_webhook_event,
    process_stripe_event,
    update_webhook_status,
)


async def handle_stripe_webhook(
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """Claim, process, and persist the final status for a Stripe webhook event."""
    claimed = await claim_webhook_event(event_id, event_type, db)
    if not claimed:
        return {
            "event_id": event_id,
            "event_type": event_type,
            "status": "duplicate",
        }

    try:
        final_status = await process_stripe_event(event_type, payload, db)
    except Exception as exc:
        await update_webhook_status(event_id, "failed", str(exc), db)
        raise

    await update_webhook_status(event_id, final_status, None, db)
    return {
        "event_id": event_id,
        "event_type": event_type,
        "status": final_status,
    }


async def get_webhook_status(event_id: str, db: AsyncSession) -> dict[str, Any] | None:
    event = await get_webhook_event(event_id, db)
    if event is None:
        return None
    return {
        "event_id": event.stripe_event_id,
        "event_type": event.event_type,
        "status": event.status,
        "error": event.error,
    }
