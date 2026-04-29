"""
backend/api/routers/contact.py

Contact form endpoint.
- Validates input
- Sends notification email via Resend
- Falls back gracefully if email not configured
- Always returns 200 to prevent enumeration
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, field_validator

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
        v = v.strip()
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
    Always returns 200 to avoid enumeration.
    Logs submission regardless of email delivery.
    """
    ip = request.client.host if request.client else "unknown"
    subject_label = SUBJECTS.get(body.subject, body.subject)

    logger.info(
        f"[contact] New message from {body.email} | subject={body.subject} | ip={ip}"
    )

    # Build admin notification email
    html = f"""
    <div style="font-family:sans-serif;max-width:600px">
      <h2>Nouveau message de contact — Nanovia OS</h2>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:8px;font-weight:bold">Nom</td><td style="padding:8px">{body.name}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">Email</td><td style="padding:8px">{body.email}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">Sujet</td><td style="padding:8px">{subject_label}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">IP</td><td style="padding:8px">{ip}</td></tr>
      </table>
      <h3>Message:</h3>
      <div style="background:#f5f5f5;padding:16px;border-radius:6px;white-space:pre-wrap">{body.message}</div>
    </div>
    """

    try:
        from api.config import settings
        admin_email = settings.RESEND_FROM_EMAIL
        await send_email(
            to=admin_email,
            subject=f"[Nanovia Contact] {subject_label} — {body.name}",
            html=html,
        )
    except Exception as exc:
        # Email delivery failure — still logged above, not a fatal error
        logger.warning(f"[contact] Email delivery failed: {exc}")

    # Always return success — never reveal delivery status
    return {"received": True, "message": "Ton message a été reçu. Nous te répondrons bientôt."}
