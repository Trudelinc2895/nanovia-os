"""
backend/api/services/subscription_state_machine.py
Explicit subscription state machine for Nanovia OS.

State transitions handled here:
  trialing  ──► active           (trial_will_end warning → handle_trial_will_end)
  trialing  ──► active/free      (trial_end → handle_trial_end)
  active    ──► past_due         (payment_failed → handle_payment_failed)
  past_due  ──► active           (payment recovered → handle_subscription_update)
  active    ──► canceled         (user cancels → handle_subscription_update)
  any       ──► downgraded_free  (invoice.payment_failed multiple → handle_subscription_update)

The underlying Stripe sync lives in billing_service.sync_subscription_from_stripe().
This module adds explicit BUSINESS LOGIC on top of those transitions:
  - email notifications
  - in-app audit entries
  - plan degradation side effects

RULES:
  - All DB mutations go through existing services (credit_service, billing_service)
  - No direct writes to user.plan / user.credits here
  - Functions are idempotent (safe to retry from webhook)
"""
from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.subscription import Subscription
from api.models.user import User

logger = logging.getLogger(__name__)


# ─── State enum ───────────────────────────────────────────────────────────────

class SubscriptionState(str, Enum):
    """Normalized subscription states used across the application."""
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    INACTIVE = "inactive"   # No subscription row at all


# Stripe statuses that map to "effectively active" for feature access
_ACTIVE_LIKE = {SubscriptionState.ACTIVE, SubscriptionState.TRIALING, SubscriptionState.PAST_DUE}

# Stripe statuses that degrade user to free plan
_DEGRADE_TO_FREE = {SubscriptionState.CANCELED, SubscriptionState.UNPAID, SubscriptionState.INCOMPLETE_EXPIRED}


def get_subscription_state(sub: Subscription | None) -> SubscriptionState:
    """
    Resolve the current subscription state from an ORM Subscription row.
    Returns INACTIVE if no subscription exists.
    """
    if sub is None:
        return SubscriptionState.INACTIVE
    try:
        return SubscriptionState(sub.status)
    except ValueError:
        logger.warning(f"[fsm] Unknown subscription status '{sub.status}' — treating as INACTIVE")
        return SubscriptionState.INACTIVE


def is_access_granted(sub: Subscription | None) -> bool:
    """
    Return True if the subscription grants feature access (active, trialing, or past_due).
    Past_due keeps access during Stripe's retry grace period.
    """
    state = get_subscription_state(sub)
    return state in _ACTIVE_LIKE


# ─── Primary webhook event handler ───────────────────────────────────────────

async def handle_subscription_event(stripe_event: dict[str, Any], db: AsyncSession) -> None:
    """
    Route a Stripe subscription-related event to the appropriate handler.
    Called from billing.py webhook handler.

    Supported event types:
      - customer.subscription.created
      - customer.subscription.updated
      - customer.subscription.deleted
    """
    from api.services.billing_service import sync_subscription_from_stripe

    event_type = stripe_event.get("type", "")
    stripe_sub = stripe_event.get("data", {}).get("object", {})

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        await sync_subscription_from_stripe(stripe_sub, db)
        logger.info(f"[fsm] Handled {event_type} sub={stripe_sub.get('id')}")
    else:
        logger.debug(f"[fsm] Skipping unhandled event type: {event_type}")


# ─── Trial handlers ────────────────────────────────────────────────────────────

async def handle_trial_will_end(
    user: User,
    sub: Subscription,
    days_remaining: int,
    db: AsyncSession,
) -> None:
    """
    Called when Stripe fires customer.subscription.trial_will_end (3 days before).

    Actions:
    1. Send trial-ending email (non-blocking)
    2. Write audit log entry
    """
    from api.services.billing_service import _write_audit  # type: ignore[attr-defined]
    from api.services.email_service import send_trial_ending

    logger.info(
        f"[fsm] trial_will_end user={user.id} plan={sub.plan} days_remaining={days_remaining}"
    )

    # Fire email asynchronously — never block on it
    asyncio.create_task(
        send_trial_ending(user.email, user.full_name or user.email, days_remaining)
    )

    await _write_audit(
        db, user.id,
        action="trial_will_end",
        detail=f"days_remaining={days_remaining} plan={sub.plan}",
    )


async def handle_trial_end(user: User, db: AsyncSession) -> None:
    """
    Called when a trial period has ended (subscription status transitions from
    trialing to active OR to past_due if no payment method is on file).

    The plan sync has already happened via sync_subscription_from_stripe().
    This handler fires supplementary notifications only.
    """
    from api.services.billing_service import _write_audit  # type: ignore[attr-defined]

    logger.info(f"[fsm] trial_end user={user.id} current_plan={user.plan}")

    await _write_audit(
        db, user.id,
        action="trial_ended",
        detail=f"plan={user.plan}",
    )


# ─── Payment failure handler ──────────────────────────────────────────────────

async def handle_payment_failed(
    user: User,
    sub: Subscription | None,
    db: AsyncSession,
) -> None:
    """
    Called when Stripe fires invoice.payment_failed.

    Actions:
    1. Send payment-failed email (non-blocking)
    2. Write audit log
    3. Does NOT degrade plan — Stripe retries and we keep past_due grace period.
       Plan degradation only happens on subscription.deleted / unpaid.
    """
    from api.services.billing_service import _write_audit  # type: ignore[attr-defined]
    from api.services.email_service import send_payment_failed

    plan = sub.plan if sub else user.plan
    logger.warning(
        f"[fsm] payment_failed user={user.id} plan={plan} "
        f"sub={sub.stripe_subscription_id if sub else 'none'}"
    )

    asyncio.create_task(
        send_payment_failed(user.email, plan)
    )

    await _write_audit(
        db, user.id,
        action="payment_failed",
        detail=f"plan={plan} sub={sub.stripe_subscription_id if sub else 'none'}",
    )


# ─── Cancellation handler ─────────────────────────────────────────────────────

async def handle_subscription_canceled(
    user: User,
    sub: Subscription,
    db: AsyncSession,
) -> None:
    """
    Called when a subscription moves to canceled state.

    Plan degradation has already been applied by sync_subscription_from_stripe()
    (user.plan → "free"). This handler fires notifications.
    """
    from api.services.billing_service import _write_audit  # type: ignore[attr-defined]

    logger.info(f"[fsm] subscription_canceled user={user.id} sub={sub.stripe_subscription_id}")

    await _write_audit(
        db, user.id,
        action="subscription_canceled",
        detail=f"stripe_sub={sub.stripe_subscription_id}",
    )
