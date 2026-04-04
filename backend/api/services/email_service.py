"""
backend/api/services/email_service.py
Transactional email via Resend API (https://api.resend.com/emails).
Falls back gracefully (log-only) when RESEND_API_KEY is not configured.
"""
from __future__ import annotations

import logging

import httpx

from api.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_FROM = "KT Monetization OS <noreply@tkverse.ca>"
_DASHBOARD_URL = f"{settings.PUBLIC_WEB_URL}/dashboard"
_UPDATE_PAYMENT_URL = f"{settings.PUBLIC_WEB_URL}/dashboard/billing"

# ─── Shared helpers ────────────────────────────────────────────────────────────

def _btn(url: str, label: str) -> str:
    return (
        f'<a href="{url}" style="display:inline-block;padding:12px 28px;'
        'background:#7C3AED;color:#fff;font-weight:700;border-radius:8px;'
        'text-decoration:none;font-size:15px;letter-spacing:.3px;">'
        f"{label}</a>"
    )


def _wrap(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>KT Monetization OS</title>
</head>
<body style="margin:0;padding:0;background:#0D0D0D;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0D0D0D;padding:40px 0;">
    <tr><td align="center">
      <table width="580" cellpadding="0" cellspacing="0"
             style="background:#141414;border-radius:12px;border:1px solid #2A2A2A;overflow:hidden;">
        <tr>
          <td style="background:#7C3AED;padding:20px 32px;">
            <span style="color:#fff;font-size:20px;font-weight:800;letter-spacing:.5px;">
              ⚡ KT Monetization OS
            </span>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 32px;color:#E5E7EB;line-height:1.7;font-size:15px;">
            {body}
          </td>
        </tr>
        <tr>
          <td style="padding:20px 32px;border-top:1px solid #2A2A2A;">
            <p style="margin:0;color:#6B7280;font-size:12px;">
              © KT Monetization OS · tkverse.ca · Vous recevez cet e-mail car vous avez
              créé un compte ou souscrit à un abonnement.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


async def _send(to: str, subject: str, html: str) -> bool:
    """POST to Resend API. Returns True on success, False on any failure."""
    if not settings.RESEND_API_KEY:
        logger.info("[email] RESEND_API_KEY not set — skipping send to %s | %s", to, subject)
        return False

    payload = {"from": _FROM, "to": [to], "subject": subject, "html": html}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            )
        if resp.is_success:
            logger.info("[email] Sent '%s' to %s (id=%s)", subject, to, resp.json().get("id"))
            return True
        logger.warning("[email] Resend error %s for '%s' → %s", resp.status_code, subject, resp.text)
        return False
    except Exception as exc:
        logger.error("[email] Failed to send '%s' to %s: %s", subject, to, exc)
        return False


# ─── Public API ────────────────────────────────────────────────────────────────

async def send_welcome_email(to: str, name: str) -> bool:
    """Send onboarding welcome email after successful registration."""
    display = name or to
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        Bienvenue sur KT Monetization OS ⚡
      </h1>
      <p style="margin:0 0 12px;">
        Salut <strong style="color:#A78BFA;">{display}</strong> 👋,
      </p>
      <p style="margin:0 0 12px;">
        Ton compte est prêt. Accède à ton tableau de bord pour commencer à
        monétiser tes projets, gérer tes modules et suivre tes revenus en temps réel.
      </p>
      <p style="margin:0 0 28px;">
        Tout est en place — il ne te reste qu'à lancer. 🚀
      </p>
      {_btn(_DASHBOARD_URL, "Accéder au Dashboard →")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Des questions ? Réponds directement à cet e-mail, on est là.
      </p>
    """)
    return await _send(to, "Bienvenue sur KT Monetization OS ⚡", html)


async def send_password_reset_email(to: str, reset_url: str) -> bool:
    """Send password reset email with a tokenized link."""
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        🔐 Réinitialisation de mot de passe
      </h1>
      <p style="margin:0 0 12px;">
        Tu as demandé à réinitialiser le mot de passe de ton compte KT Monetization OS.
      </p>
      <p style="margin:0 0 28px;">
        Clique sur le bouton ci-dessous. Ce lien expire dans <strong>1 heure</strong>.
      </p>
      {_btn(reset_url, "Réinitialiser mon mot de passe →")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Si tu n'as pas fait cette demande, ignore cet e-mail — ton compte est en sécurité.
      </p>
    """)
    return await _send(to, "🔐 Réinitialisation de mot de passe", html)


async def send_subscription_email(to: str, plan: str, amount: float) -> bool:
    """Send subscription activation confirmation email."""
    plan_display = plan.capitalize()
    amount_str = f"${amount:.2f} USD"
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        ✅ Abonnement activé — Plan {plan_display}
      </h1>
      <p style="margin:0 0 20px;">
        Merci pour ta confiance ! Ton abonnement est maintenant actif.
      </p>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="background:#1F1F1F;border-radius:8px;border:1px solid #2A2A2A;
                    margin-bottom:28px;">
        <tr>
          <td style="padding:16px 20px;border-bottom:1px solid #2A2A2A;">
            <span style="color:#9CA3AF;">Plan</span>
            <span style="float:right;color:#F9FAFB;font-weight:700;">{plan_display}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 20px;border-bottom:1px solid #2A2A2A;">
            <span style="color:#9CA3AF;">Montant</span>
            <span style="float:right;color:#A78BFA;font-weight:700;">{amount_str}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 20px;">
            <span style="color:#9CA3AF;">Statut</span>
            <span style="float:right;color:#34D399;font-weight:700;">✅ Actif</span>
          </td>
        </tr>
      </table>
      {_btn(_DASHBOARD_URL, "Voir mon Dashboard →")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Tu peux gérer ton abonnement à tout moment depuis le portail de facturation.
      </p>
    """)
    return await _send(to, f"✅ Abonnement activé — Plan {plan_display}", html)


async def send_payment_failed(to: str, plan: str) -> bool:
    """Send payment failure notification email."""
    plan_display = plan.capitalize()
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        ⚠️ Échec de paiement
      </h1>
      <p style="margin:0 0 12px;">
        Nous n'avons pas pu traiter le paiement pour ton abonnement
        <strong style="color:#A78BFA;">Plan {plan_display}</strong>.
      </p>
      <p style="margin:0 0 12px;">
        Stripe réessaiera automatiquement, mais nous te recommandons de mettre
        à jour tes informations de paiement dès maintenant pour éviter toute
        interruption de service.
      </p>
      <p style="margin:0 0 28px;color:#F87171;font-weight:600;">
        ⚠️ Ton accès pourrait être limité si le paiement reste en échec.
      </p>
      {_btn(_UPDATE_PAYMENT_URL, "Mettre à jour le paiement →")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Si tu penses qu'il s'agit d'une erreur, contacte-nous en répondant à cet e-mail.
      </p>
    """)
    return await _send(to, "⚠️ Échec de paiement — Action requise", html)


# Alias for billing router compatibility
send_billing_confirmation = send_subscription_email
