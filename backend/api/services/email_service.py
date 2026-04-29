"""
backend/api/services/email_service.py
Transactional email via Resend API (https://api.resend.com/emails).
Falls back gracefully (log-only) when RESEND_API_KEY is not configured.
"""
from __future__ import annotations

import logging

import httpx
from markupsafe import escape

from api.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
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
  <title>Nanovia OS</title>
</head>
<body style="margin:0;padding:0;background:#0D0D0D;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0D0D0D;padding:40px 0;">
    <tr><td align="center">
      <table width="580" cellpadding="0" cellspacing="0"
             style="background:#141414;border-radius:12px;border:1px solid #2A2A2A;overflow:hidden;">
        <tr>
          <td style="background:#7C3AED;padding:20px 32px;">
            <span style="color:#fff;font-size:20px;font-weight:800;letter-spacing:.5px;">
              ⚡ Nanovia OS
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
              © Nanovia OS · nanovia.ca · Vous recevez cet e-mail car vous avez
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

    payload = {"from": settings.RESEND_FROM, "to": [to], "subject": subject, "html": html}
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
    display = str(escape(name or to))
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        Bienvenue sur Nanovia OS ⚡
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
    return await _send(to, "Bienvenue sur Nanovia OS ⚡", html)


async def send_password_reset_email(to: str, reset_url: str) -> bool:
    """Send password reset email with a tokenized link."""
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        🔐 Réinitialisation de mot de passe
      </h1>
      <p style="margin:0 0 12px;">
        Tu as demandé à réinitialiser le mot de passe de ton compte Nanovia OS.
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


async def send_trial_ending(to: str, name: str, days_left: int) -> bool:
    """Notify user that their trial ends in N days."""
    display = name or to
    plural = "jour" if days_left == 1 else "jours"
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        Ta periode d'essai se termine dans {days_left} {plural}
      </h1>
      <p style="margin:0 0 12px;">
        Salut <strong style="color:#A78BFA;">{display}</strong>,
      </p>
      <p style="margin:0 0 12px;">
        Ta periode d'essai expire dans
        <strong style="color:#FBBF24;">{days_left} {plural}</strong>.
        Pour continuer sans interruption, active ton abonnement maintenant.
      </p>
      <p style="margin:0 0 28px;">
        Profite de <strong>-20% sur le plan annuel</strong>, disponible depuis ton dashboard.
      </p>
      {_btn(_DASHBOARD_URL + "/billing", "Activer mon abonnement")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Des questions ? Reponds directement a cet e-mail.
      </p>
    """)
    return await _send(to, f"Periode d'essai : {days_left} {plural} restant(s)", html)


async def send_usage_alert(to: str, name: str, pct: int, plan: str) -> bool:
    """Notify user they have reached 80%+ of their monthly usage limit."""
    display = name or to
    plan_display = plan.capitalize()
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        Quota mensuel : {pct}% utilise
      </h1>
      <p style="margin:0 0 12px;">
        Salut <strong style="color:#A78BFA;">{display}</strong>,
      </p>
      <p style="margin:0 0 12px;">
        Tu as consomme <strong style="color:#FBBF24;">{pct}%</strong> de tes messages
        inclus dans le plan <strong>{plan_display}</strong>.
      </p>
      <p style="margin:0 0 12px;">
        Une fois la limite atteinte, tes credits d'overage seront debites automatiquement.
        Tu peux aussi upgrader ton plan pour obtenir plus de messages.
      </p>
      {_btn(_DASHBOARD_URL + "/billing", "Voir mon usage")}
    """)
    return await _send(to, f"Alerte quota — {pct}% utilise ce mois", html)


async def send_subscription_cancelled(to: str, name: str, plan: str) -> bool:
    """Notify user their subscription has been cancelled."""
    display = name or to
    plan_display = plan.capitalize()
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        Abonnement annulé
      </h1>
      <p style="margin:0 0 12px;">
        Salut <strong style="color:#A78BFA;">{display}</strong>,
      </p>
      <p style="margin:0 0 12px;">
        Ton abonnement <strong style="color:#F87171;">Plan {plan_display}</strong>
        a été annulé. Tu garderas accès à tes fonctionnalités jusqu'à la fin
        de ta période de facturation en cours.
      </p>
      <p style="margin:0 0 28px;">
        Tu peux te réabonner à tout moment depuis ton tableau de bord.
      </p>
      {_btn(_DASHBOARD_URL + "/billing", "Gérer mon abonnement")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Une question ? Réponds à cet e-mail, nous sommes là pour toi.
      </p>
    """)
    return await _send(to, "Abonnement Nanovia annulé", html)


async def send_low_credits(to: str, name: str, balance: int) -> bool:
    """Notify user their overage credit balance is critically low (less than 3)."""
    display = name or to
    plural = "credit" if balance <= 1 else "credits"
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        Credits d'overage presque epuises
      </h1>
      <p style="margin:0 0 12px;">
        Salut <strong style="color:#A78BFA;">{display}</strong>,
      </p>
      <p style="margin:0 0 12px;">
        Il te reste seulement
        <strong style="color:#F87171;">{balance} {plural}</strong> d'overage.
        Une fois epuises, les requetes au-dela de ta limite mensuelle seront bloquees.
      </p>
      <p style="margin:0 0 28px;">
        Recharge maintenant pour eviter toute interruption.
      </p>
      {_btn(_DASHBOARD_URL + "/billing", "Recharger mes credits")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Packs disponibles a partir de 4$ / 50 credits.
      </p>
    """)
    return await _send(to, "Alerte credits — rechargement requis", html)


async def send_verification_email(to_email: str, name: str, verify_url: str) -> None:
    """Send email verification link after registration."""
    subject = "Vérifie ton adresse email — Nanovia OS"
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2>Confirme ton email</h2>
      <p>Salut {name or to_email},</p>
      <p>Clique sur le bouton ci-dessous pour activer ton compte Nanovia OS :</p>
      <a href="{verify_url}" style="display:inline-block;padding:12px 28px;background:#4F46E5;color:#fff;border-radius:6px;text-decoration:none;font-weight:bold">
        Vérifier mon email
      </a>
      <p style="margin-top:24px;color:#666;font-size:12px">
        Ce lien expire dans 24 heures.<br>
        Si tu n'as pas créé de compte, ignore ce message.
      </p>
    </div>
    """
    await _send(to_email, subject, html)


# Alias for billing router compatibility
send_billing_confirmation = send_subscription_email


async def send_team_invitation(to: str, inviter_name: str, invite_url: str) -> bool:
    """Send team invitation email with branded HTML template."""
    inviter_display = str(escape(inviter_name or "Un membre de l'équipe"))
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        👥 Tu as été invité(e) à rejoindre une équipe
      </h1>
      <p style="margin:0 0 12px;">
        <strong style="color:#A78BFA;">{inviter_display}</strong> t'invite à rejoindre
        son espace de travail sur <strong>Nanovia OS</strong>.
      </p>
      <p style="margin:0 0 28px;">
        Clique sur le bouton ci-dessous pour accepter l'invitation et accéder
        à votre espace collaboratif.
      </p>
      {_btn(invite_url, "Rejoindre l'équipe →")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Si tu ne connais pas cette personne, ignore ce message.
        Ce lien expire dans <strong>48 heures</strong>.
      </p>
    """)
    return await _send(to, f"👥 {inviter_display} t'invite à rejoindre Nanovia OS", html)


async def send_custom_module_created(to: str, name: str, module_name: str) -> bool:
    """Notify user that their custom module has been created successfully."""
    display = str(escape(name or to))
    module_display = str(escape(module_name))
    modules_url = f"{_DASHBOARD_URL}/modules/custom"
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        ✨ Module personnalisé créé
      </h1>
      <p style="margin:0 0 12px;">
        Salut <strong style="color:#A78BFA;">{display}</strong> 👋,
      </p>
      <p style="margin:0 0 12px;">
        Ton module IA personnalisé <strong style="color:#A78BFA;">«&nbsp;{module_display}&nbsp;»</strong>
        a été créé avec succès et est maintenant disponible dans ton espace.
      </p>
      <p style="margin:0 0 28px;">
        Tu peux l'utiliser, le modifier ou en créer d'autres depuis ton tableau de bord.
      </p>
      {_btn(modules_url, "Voir mes modules →")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Des questions ? Réponds directement à cet e-mail.
      </p>
    """)
    return await _send(to, f"✨ Module «{module_name}» créé avec succès", html)


async def send_plan_downgraded(to: str, name: str, old_plan: str, new_plan: str) -> bool:
    """Notify user that their plan has been downgraded."""
    display = str(escape(name or to))
    old_display = old_plan.capitalize()
    new_display = new_plan.capitalize()
    html = _wrap(f"""
      <h1 style="margin:0 0 16px;color:#F9FAFB;font-size:24px;font-weight:800;">
        📉 Changement de plan
      </h1>
      <p style="margin:0 0 12px;">
        Salut <strong style="color:#A78BFA;">{display}</strong>,
      </p>
      <p style="margin:0 0 12px;">
        Ton abonnement a été modifié :
        <strong style="color:#F87171;">Plan {old_display}</strong>
        → <strong style="color:#A78BFA;">Plan {new_display}</strong>.
      </p>
      <p style="margin:0 0 12px;">
        Certaines fonctionnalités peuvent ne plus être disponibles.
        Ton accès sera mis à jour à la fin de ta période de facturation en cours.
      </p>
      <p style="margin:0 0 28px;">
        Tu peux upgrader à nouveau à tout moment depuis ton tableau de bord.
      </p>
      {_btn(_DASHBOARD_URL + "/billing", "Gérer mon abonnement →")}
      <p style="margin:28px 0 0;color:#9CA3AF;font-size:13px;">
        Une question ? Réponds à cet e-mail, nous sommes là pour toi.
      </p>
    """)
    return await _send(to, f"📉 Ton plan a changé : {old_display} → {new_display}", html)

