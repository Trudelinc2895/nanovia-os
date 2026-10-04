"""Durable, idempotent notifications for Nanovia Pro Pilot operations."""
from __future__ import annotations

import logging

from markupsafe import escape
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models.pilot import PilotPayment, PilotRequest
from api.services.email_service import _send as send_email
from api.services.email_service import _wrap as wrap_email


logger = logging.getLogger(__name__)
MAX_NOTIFICATION_ATTEMPTS = 6


def _safe(value: object | None, fallback: str = "—") -> str:
    raw = str(value).strip() if value is not None else ""
    return str(escape(raw or fallback))


def _row(label: str, value: object | None) -> str:
    return (
        '<tr><td style="padding:8px;font-weight:bold;vertical-align:top">'
        f"{_safe(label)}</td><td style=\"padding:8px\">{_safe(value)}</td></tr>"
    )


def _operator_intake_html(request: PilotRequest) -> str:
    rows = "".join(
        (
            _row("Référence", request.id),
            _row("Nom", request.name),
            _row("Entreprise", request.company),
            _row("Courriel", request.email),
            _row("Activité", request.business_type),
            _row("Urgence", request.urgency),
            _row("Tâche", request.repetitive_task or request.message),
            _row("Exemples", request.examples),
            _row("Objectif", request.goal),
        )
    )
    return wrap_email(
        "<h1 style=\"margin:0 0 18px;color:#F9FAFB;font-size:24px\">"
        "Nouvelle demande Pro Pilot</h1>"
        f"<table style=\"width:100%;border-collapse:collapse\">{rows}</table>"
        "<p style=\"margin:20px 0 0;color:#9CA3AF\">"
        "Répondez directement à ce courriel pour joindre le client.</p>"
    )


def _client_intake_html(request: PilotRequest) -> str:
    return wrap_email(
        "<h1 style=\"margin:0 0 18px;color:#F9FAFB;font-size:24px\">"
        "Votre demande est bien enregistrée</h1>"
        f"<p>Bonjour <strong>{_safe(request.name)}</strong>,</p>"
        "<p>Nanovia a reçu votre demande Pro Pilot. Elle est conservée même si "
        "un service de notification devient temporairement indisponible.</p>"
        f"<p>Référence : <strong>{_safe(request.id)}</strong></p>"
        "<p>Prochaine étape : finaliser le paiement sécurisé depuis la page de "
        "confirmation affichée après l’envoi du formulaire. Une réponse peut être "
        "faite directement à ce courriel si une précision est nécessaire.</p>"
    )


def _operator_payment_html(request: PilotRequest) -> str:
    return wrap_email(
        "<h1 style=\"margin:0 0 18px;color:#34D399;font-size:24px\">"
        "Paiement Pro Pilot confirmé</h1>"
        f"<p>Référence : <strong>{_safe(request.id)}</strong></p>"
        f"<p>Client : <strong>{_safe(request.name)}</strong> — {_safe(request.company)}</p>"
        f"<p>Tâche : {_safe(request.repetitive_task or request.message)}</p>"
        "<p>La demande est maintenant qualifiée dans le centre Pilot.</p>"
    )


def _client_payment_html(request: PilotRequest, amount_cents: int) -> str:
    amount = f"{amount_cents // 100},{amount_cents % 100:02d}"
    return wrap_email(
        "<h1 style=\"margin:0 0 18px;color:#34D399;font-size:24px\">"
        "Paiement confirmé — démarrage du Pro Pilot</h1>"
        f"<p>Bonjour <strong>{_safe(request.name)}</strong>,</p>"
        f"<p>Votre paiement de {amount} $ CAD est confirmé. Votre demande passe dans "
        "la file de préparation Nanovia.</p>"
        f"<p>Référence : <strong>{_safe(request.id)}</strong></p>"
        "<p>Conservez ce courriel. Nanovia utilisera cette adresse pour les "
        "questions nécessaires à la configuration et pour le suivi de livraison.</p>"
    )


async def deliver_intake_notifications(request: PilotRequest) -> dict[str, bool]:
    """Deliver operator + client intake emails and persistable outcomes."""
    recipient = settings.CONTACT_RECIPIENT_EMAIL.strip()
    request.routed_to = recipient or None
    attempted = False
    results = {
        "operator": request.notification_status == "sent",
        "client": request.client_notification_status == "sent",
    }

    if request.notification_status != "sent":
        attempted = True
        try:
            results["operator"] = await send_email(
                to=recipient,
                subject=f"[Nanovia Pilot][{(request.urgency or 'moyen').upper()}] {request.company or request.name}",
                html=_operator_intake_html(request),
                reply_to=request.email,
                idempotency_key=f"pilot-intake-operator/{request.id}",
            )
        except Exception:
            logger.exception("[pilot-notification] Operator intake delivery failed request=%s", request.id)
            results["operator"] = False
        request.notification_status = "sent" if results["operator"] else "failed"

    if request.client_notification_status != "sent":
        attempted = True
        try:
            results["client"] = await send_email(
                to=request.email,
                subject=f"Demande Nanovia Pro Pilot reçue — {request.id}",
                html=_client_intake_html(request),
                reply_to=recipient or None,
                idempotency_key=f"pilot-intake-client/{request.id}",
            )
        except Exception:
            logger.exception("[pilot-notification] Client intake delivery failed request=%s", request.id)
            results["client"] = False
        request.client_notification_status = "sent" if results["client"] else "failed"

    if attempted:
        request.notification_attempts = (request.notification_attempts or 0) + 1
    request.last_notification_error = (
        None if all(results.values()) else "Une ou plusieurs notifications d’admission ont échoué."
    )
    return results


async def deliver_payment_notifications(request: PilotRequest, db: AsyncSession) -> bool:
    """Notify both sides once a verified Stripe payment is persisted."""
    if request.status != "paid" or request.payment_notification_status == "sent":
        return request.payment_notification_status == "sent"

    payment = (
        await db.execute(
            select(PilotPayment)
            .where(
                PilotPayment.pilot_request_id == request.id,
                PilotPayment.status == "paid",
                PilotPayment.payment_status == "paid",
            )
            .order_by(PilotPayment.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if (
        payment is None
        or payment.amount_subtotal is None
        or payment.amount_subtotal <= 0
        or payment.currency.lower() != "cad"
    ):
        request.payment_notification_status = "failed"
        request.last_notification_error = "Paiement confirmé introuvable pour la notification."
        return False

    recipient = (request.routed_to or settings.CONTACT_RECIPIENT_EMAIL).strip()
    request.payment_notification_attempts = (request.payment_notification_attempts or 0) + 1
    try:
        operator_sent = await send_email(
            to=recipient,
            subject=f"[Nanovia Pilot][PAYÉ] {request.company or request.name}",
            html=_operator_payment_html(request),
            reply_to=request.email,
            idempotency_key=f"pilot-paid-operator/{request.id}",
        )
        client_sent = await send_email(
            to=request.email,
            subject=f"Paiement Nanovia Pro Pilot confirmé — {request.id}",
            html=_client_payment_html(request, payment.amount_subtotal),
            reply_to=recipient or None,
            idempotency_key=f"pilot-paid-client/{request.id}",
        )
    except Exception:
        logger.exception("[pilot-notification] Payment delivery failed request=%s", request.id)
        operator_sent = client_sent = False

    delivered = operator_sent and client_sent
    request.payment_notification_status = "sent" if delivered else "failed"
    if delivered:
        request.last_notification_error = None
        if request.fulfillment_status == "new":
            request.fulfillment_status = "qualified"
    else:
        request.last_notification_error = "La notification de paiement a échoué."
    return delivered


async def retry_pending_pilot_notifications(db_factory) -> None:
    """Retry unsent intake/payment notifications with row-level work claiming."""
    async with db_factory() as db:
        rows = await db.execute(
            select(PilotRequest)
            .where(
                or_(
                    and_(
                        PilotRequest.notification_attempts < MAX_NOTIFICATION_ATTEMPTS,
                        or_(
                            PilotRequest.notification_status != "sent",
                            PilotRequest.client_notification_status != "sent",
                        ),
                    ),
                    and_(
                        PilotRequest.status == "paid",
                        PilotRequest.payment_notification_status != "sent",
                        PilotRequest.payment_notification_attempts < MAX_NOTIFICATION_ATTEMPTS,
                    ),
                )
            )
            .order_by(PilotRequest.created_at.asc())
            .limit(25)
            .with_for_update(skip_locked=True)
        )
        requests = rows.scalars().all()
        for pilot_request in requests:
            if (
                pilot_request.notification_attempts < MAX_NOTIFICATION_ATTEMPTS
                and (
                    pilot_request.notification_status != "sent"
                    or pilot_request.client_notification_status != "sent"
                )
            ):
                await deliver_intake_notifications(pilot_request)
            if (
                pilot_request.status == "paid"
                and pilot_request.payment_notification_status != "sent"
                and pilot_request.payment_notification_attempts < MAX_NOTIFICATION_ATTEMPTS
            ):
                await deliver_payment_notifications(pilot_request, db)
        if requests:
            await db.commit()
            logger.info("[pilot-notification] Retried %d Pilot request(s)", len(requests))
