"""
backend/api/routers/contact.py

Contact form endpoint.
- Validates input
- Sends notification email via Resend
- Returns an explicit service error when delivery is unavailable
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from markupsafe import escape
from pydantic import BaseModel, EmailStr, field_validator

from api.config import settings
from api.services.email_service import _send as send_email

logger = logging.getLogger(__name__)
router = APIRouter()

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
async def contact_form(body: ContactRequest, request: Request):
    """
    Process contact form submission.
    Only confirms receipt after the notification provider accepts the email.
    """
    ip = request.client.host if request.client else "unknown"
    subject_label = SUBJECTS.get(body.subject, body.subject)

    logger.info("[contact] New message | subject=%s | ip=%s", body.subject, ip)

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

    if not delivered:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La transmission est temporairement indisponible. Utilisez le lien courriel de secours.",
        )

    return {"received": True, "message": "Votre demande a été reçue."}
