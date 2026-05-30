"""
backend/api/services/telegram_service.py
Telegram alert delivery for production-critical events.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from api.config import settings

logger = logging.getLogger(__name__)

_TELEGRAM_URL = "https://api.telegram.org"


def telegram_alerts_enabled() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


async def send_telegram_message(text: str) -> bool:
    """Send a plain-text Telegram message. Returns False if alerts are not configured."""
    if not telegram_alerts_enabled():
        logger.info("[telegram] Alerts disabled: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return False

    url = f"{_TELEGRAM_URL}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("[telegram] Failed to send message: %s", exc)
        return False

    logger.info("[telegram] Alert delivered")
    return True


def build_stripe_event_message(
    event_type: str,
    data: dict[str, Any],
    *,
    status: str,
    user_email: str | None = None,
) -> str:
    event_id = data.get("id", "unknown")
    customer_id = data.get("customer", "unknown")
    amount_cents = data.get("amount_paid") or data.get("amount_due") or data.get("amount_total")
    amount_line = ""
    if amount_cents is not None:
        amount_line = f"\nAmount: {amount_cents / 100:.2f} USD"

    user_line = f"\nUser: {user_email}" if user_email else ""
    subscription_id = data.get("subscription") or data.get("id")
    subscription_line = f"\nSubscription: {subscription_id}" if subscription_id else ""
    attempt_line = ""
    if data.get("attempt_count") is not None:
        attempt_line = f"\nAttempt: {data.get('attempt_count')}"

    return (
        "Nanovia Stripe event\n"
        f"Type: {event_type}\n"
        f"Status: {status}\n"
        f"Event/Object: {event_id}\n"
        f"Customer: {customer_id}"
        f"{user_line}"
        f"{subscription_line}"
        f"{amount_line}"
        f"{attempt_line}"
    )


async def send_stripe_event_alert(
    event_type: str,
    data: dict[str, Any],
    *,
    status: str,
    user_email: str | None = None,
) -> bool:
    message = build_stripe_event_message(
        event_type,
        data,
        status=status,
        user_email=user_email,
    )
    return await send_telegram_message(message)
