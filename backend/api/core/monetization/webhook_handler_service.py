"""Central Stripe webhook handling for the Nanovia monetization core."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.services.billing_service import (
    WEBHOOK_CLAIMED,
    WEBHOOK_DUPLICATE,
    WEBHOOK_IN_PROGRESS,
    claim_webhook_event,
    dispatch_post_commit_actions,
    get_webhook_event,
    mark_webhook_retryable_failure,
    prepare_stripe_event,
    process_stripe_event,
    update_webhook_status,
)


class WebhookProcessingUnavailable(RuntimeError):
    """Signal a signed webhook that must be retried with HTTP 503."""


async def handle_stripe_webhook(
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """Claim, process, and persist the final status for a Stripe webhook event."""
    try:
        existing = await get_webhook_event(event_id, db)
        existing_status = getattr(existing, "status", None)
        if not isinstance(existing_status, str):
            existing_status = None
        await db.rollback()
    except Exception as exc:
        await db.rollback()
        raise WebhookProcessingUnavailable(
            "Webhook state lookup is temporarily unavailable"
        ) from exc

    if existing_status and existing_status not in {"processing", "retryable_failure"}:
        return {
            "event_id": event_id,
            "event_type": event_type,
            "status": "duplicate",
        }
    if existing_status == "processing":
        raise WebhookProcessingUnavailable("Webhook event is already being processed")

    preparation_error: Exception | None = None
    try:
        prepared_event = await prepare_stripe_event(
            event_type,
            payload,
            event_id=event_id,
        )
    except Exception as exc:
        await db.rollback()
        prepared_event = None
        preparation_error = exc

    try:
        claim_status = await claim_webhook_event(event_id, event_type, db)
    except Exception as exc:
        await db.rollback()
        raise WebhookProcessingUnavailable("Webhook claim is temporarily unavailable") from exc

    if claim_status == WEBHOOK_DUPLICATE:
        await db.rollback()
        return {
            "event_id": event_id,
            "event_type": event_type,
            "status": "duplicate",
        }
    if claim_status == WEBHOOK_IN_PROGRESS:
        await db.rollback()
        raise WebhookProcessingUnavailable("Webhook event is already being processed")
    if claim_status != WEBHOOK_CLAIMED:
        await db.rollback()
        raise WebhookProcessingUnavailable("Webhook claim returned an invalid state")

    try:
        post_commit_actions = []
        if preparation_error is not None:
            raise preparation_error
        final_status = await process_stripe_event(
            event_type,
            payload,
            db,
            event_id=event_id,
            prepared_event=prepared_event,
            post_commit_actions=post_commit_actions,
        )
        webhook_status = (
            final_status if final_status in {"ignored", "rejected"} else "processed"
        )
        await update_webhook_status(event_id, webhook_status, None, db)
        # Sole commit owner for the claim, business effects, and final status.
        await db.commit()
    except Exception as exc:
        await db.rollback()
        try:
            await mark_webhook_retryable_failure(
                event_id,
                event_type,
                str(exc)[:2000],
                db,
            )
        except Exception as marker_exc:
            await db.rollback()
            raise WebhookProcessingUnavailable(
                "Webhook processing and retry marker persistence failed"
            ) from marker_exc
        raise WebhookProcessingUnavailable(
            "Webhook processing is temporarily unavailable"
        ) from exc

    dispatch_post_commit_actions(post_commit_actions)

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
