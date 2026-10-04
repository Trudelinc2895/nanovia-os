"""
backend/api/routers/contact.py

Pilot request endpoint.
- Validates and persists the request before any notification
- Sends a best-effort notification via Resend
- Returns an opaque request_id from canonical storage
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from api.config import settings
from api.core.deps import DB
from api.models.pilot import PilotRequest
from api.services.pilot_notification_service import deliver_intake_notifications
from api.services.pilot_stripe_contract_service import (
    PilotStripeContractError,
    PilotStripeProviderUnavailable,
    load_pilot_stripe_config,
    retrieve_pilot_account,
    retrieve_pilot_payment_link,
    validate_pilot_provider_contract,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_PAYMENT_LINK_PATH = re.compile(r"^/[A-Za-z0-9_]+$")


def _sanitize_log_value(value: str | None) -> str:
    """Keep untrusted values on a single physical log line."""
    return (value or "").replace("\n", " ").replace("\r", " ")


async def _configured_payment_link_url() -> str | None:
    """Expose the current Payment Link only after live provider validation."""
    raw_value = settings.STRIPE_PILOT_PAYMENT_LINK_URL
    value = raw_value.strip()
    if not value or raw_value != value:
        return None
    try:
        config = load_pilot_stripe_config(settings)
        parsed = urlsplit(value)
        port = parsed.port
    except (PilotStripeContractError, ValueError):
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "buy.stripe.com"
        or parsed.netloc not in {"buy.stripe.com", "buy.stripe.com:443"}
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or _PAYMENT_LINK_PATH.fullmatch(parsed.path) is None
        or parsed.query
        or parsed.fragment
    ):
        return None

    try:
        account, payment_link = await asyncio.gather(
            retrieve_pilot_account(),
            retrieve_pilot_payment_link(config.payment_link_id),
        )
        validate_pilot_provider_contract(account, payment_link, config)
    except (PilotStripeContractError, PilotStripeProviderUnavailable):
        return None
    return config.payment_link_url


SUBJECTS = {
    "general": "Message général",
    "billing": "Question de facturation",
    "support": "Support technique",
    "partnership": "Partenariat",
    "demo": "Demande de démonstration",
    "bug": "Bug report",
    "other": "Autre",
}


class ContactRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100)
    company: str = Field(min_length=2, max_length=100)
    email: EmailStr
    subject: str
    message: str = Field(min_length=10, max_length=4000)
    business_type: str = Field(min_length=2, max_length=120)
    repetitive_task: str = Field(min_length=10, max_length=700)
    examples: str = Field(min_length=10, max_length=1200)
    goal: str = Field(min_length=10, max_length=700)
    urgency: Literal["faible", "moyen", "eleve", "urgent"]
    consent: bool
    company_url: str = Field(default="", max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        if v not in SUBJECTS:
            raise ValueError(f"Sujet invalide. Valeurs acceptées: {list(SUBJECTS)}")
        return v

    @field_validator("consent")
    @classmethod
    def validate_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Le consentement est requis.")
        return value

    @field_validator("company_url")
    @classmethod
    def validate_honeypot(cls, value: str) -> str:
        if value:
            raise ValueError("Soumission invalide.")
        return value


@router.post("/contact")
async def contact_form(body: ContactRequest, request: Request, db: DB):
    """
    Persist a Pilot request, then send a non-canonical notification.
    """
    ip = request.client.host if request.client else "unknown"
    logger.info(
        "[contact] New message | subject=%s | ip=%s",
        _sanitize_log_value(body.subject),
        _sanitize_log_value(ip),
    )

    pilot_request = PilotRequest(
        name=body.name,
        email=str(body.email).strip().lower(),
        subject=body.subject,
        message=body.message,
        company=body.company,
        business_type=body.business_type,
        repetitive_task=body.repetitive_task,
        examples=body.examples,
        goal=body.goal,
        urgency=body.urgency,
        consented_at=datetime.now(timezone.utc),
        status="pending",
        fulfillment_status="new",
        notification_status="pending",
        client_notification_status="pending",
        payment_notification_status="pending",
    )
    try:
        db.add(pilot_request)
        await db.commit()
        request_id = str(pilot_request.id)
    except Exception as exc:
        await db.rollback()
        logger.exception("[contact] Pilot request persistence failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La demande ne peut pas être enregistrée pour le moment.",
        ) from exc

    # Payment remains disabled unless the live Stripe Account -> Payment Link ->
    # Price -> Product contract is valid at the moment we would expose checkout.
    payment_link_url = await _configured_payment_link_url()

    try:
        notification_result = await deliver_intake_notifications(pilot_request)
    except Exception as exc:
        logger.warning("[contact] Notification delivery failed: %s", exc)
        notification_result = {"operator": False, "client": False}
        pilot_request.notification_status = "failed"
        pilot_request.client_notification_status = "failed"
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("[contact] Notification status update failed: %s", exc)

    return {
        "received": True,
        "request_id": request_id,
        "payment_link_url": payment_link_url,
        "notification_sent": notification_result["operator"],
        "acknowledgement_sent": notification_result["client"],
        "message": "Votre demande a été enregistrée.",
    }
