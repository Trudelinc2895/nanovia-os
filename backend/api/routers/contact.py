"""
backend/api/routers/contact.py

Pilot request endpoint.
- Validates and persists the request before any notification
- Sends a best-effort notification via Resend
- Returns an opaque request_id from canonical storage
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from markupsafe import escape
from pydantic import BaseModel, EmailStr, field_validator

from api.config import settings
from api.core.deps import DB
from api.models.pilot import PilotRequest
from api.services.email_service import _send as send_email

logger = logging.getLogger(__name__)
router = APIRouter()


def _sanitize_log_value(value: str | None) -> str:
    """Keep untrusted values on a single physical log line."""
    return (value or "").replace("\n", " ").replace("\r", " ")


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
    name: str
    email: EmailStr
    subject: str
    message: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v or len(v) < 2:
            raise ValueError("Le nom doit faire au moins 2 caractères.")
        if len(v) > 100:
            raise ValueError("Le nom est trop long.")
        return v

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        if v not in SUBJECTS:
            raise ValueError(f"Sujet invalide. Valeurs acceptées: {list(SUBJECTS)}")
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) < 10:
            raise ValueError("Le message doit faire au moins 10 caractères.")
        if len(v) > 4000:
            raise ValueError("Le message est trop long (max 4000 chars).")
        return v


@router.post("/contact")
async def contact_form(body: ContactRequest, request: Request, db: DB):
    """
    Persist a Pilot request, then send a non-canonical notification.
    """
    ip = request.client.host if request.client else "unknown"
    subject_label = SUBJECTS.get(body.subject, body.subject)

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
        status="pending",
        notification_status="pending",
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

    safe_name = str(escape(body.name))
    safe_email = str(escape(str(body.email)))
    safe_subject = str(escape(subject_label))
    safe_message = str(escape(body.message))

    # Escape all visitor-controlled fields before inserting them into HTML.
    html = f"""
    <div style="font-family:sans-serif;max-width:600px">
      <h2>Nouvelle demande — Nanovia Pro Pilot</h2>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:8px;font-weight:bold">Nom</td><td style="padding:8px">{safe_name}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">Email</td><td style="padding:8px">{safe_email}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">Sujet</td><td style="padding:8px">{safe_subject}</td></tr>
      </table>
      <h3>Message:</h3>
      <div style="background:#f5f5f5;padding:16px;border-radius:6px;white-space:pre-wrap">{safe_message}</div>
    </div>
    """

    try:
        delivered = await send_email(
            to=settings.CONTACT_RECIPIENT_EMAIL,
            subject=f"[Nanovia Pro Pilot] {subject_label} — {body.name}",
            html=html,
        )
    except Exception as exc:
        logger.warning("[contact] Email delivery failed: %s", exc)
        delivered = False

    pilot_request.notification_status = "sent" if delivered else "failed"
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("[contact] Notification status update failed: %s", exc)

    return {
        "received": True,
        "request_id": request_id,
        "notification_sent": delivered,
        "message": "Votre demande a été enregistrée.",
    }
