"""
backend/api/services/ghost_agency_service.py — Module 4 Ghost Agency AI service
"""
from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Tu es un expert en copywriting B2B et B2C spécialisé dans la prospection commerciale. "
    "Tu crées des messages de prospection ultra-personnalisés, directs et engageants. "
    "Chaque message doit capter l'attention immédiatement, résonner avec la douleur spécifique "
    "du prospect et proposer une valeur claire. "
    "Tu réponds UNIQUEMENT avec un objet JSON valide (sans markdown, sans texte autour) "
    "contenant exactement les clés: message, hook, personalization_notes."
)

_FALLBACK_TEMPLATES: dict[str, str] = {
    "linkedin": (
        "Bonjour {name}, j'ai remarqué votre travail dans {niche}. "
        "Je serais ravi d'échanger sur comment vous aider à atteindre vos objectifs. "
        "Seriez-vous disponible pour un appel de 15 min cette semaine ?"
    ),
    "instagram": (
        "Salut {name} 👋 Votre contenu sur {niche} est vraiment inspirant ! "
        "J'ai quelque chose qui pourrait vous intéresser — envie d'en discuter ?"
    ),
    "twitter": (
        "Hey {name}, votre perspective sur {niche} est rafraîchissante. "
        "J'aimerais vous partager quelque chose qui pourrait vous aider. DM ouvert ?"
    ),
    "email": (
        "Bonjour {name},\n\n"
        "J'ai suivi votre parcours dans {niche} et je suis impressionné par votre vision.\n\n"
        "J'aurais une proposition concrète pour vous aider à franchir un palier. "
        "Seriez-vous disponible pour un échange rapide ?\n\n"
        "Cordialement"
    ),
}


def _build_fallback(lead: dict) -> dict:
    platform = lead.get("platform", "email")
    template = _FALLBACK_TEMPLATES.get(platform, _FALLBACK_TEMPLATES["email"])
    message = template.format(name=lead.get("name", ""), niche=lead.get("niche", ""))
    hook = message[:50]
    return {
        "message": message,
        "hook": hook,
        "personalization_notes": "Message généré depuis un template de secours (OpenAI indisponible).",
    }


async def generate_outreach_message(
    lead: dict,
    campaign_context: str,
    openai_key: str,
) -> dict:
    """
    Generate a personalized outreach message via OpenAI gpt-4o-mini.

    Args:
        lead: dict with keys name, niche, platform, pain_points, goals, context
        campaign_context: additional context for the campaign
        openai_key: OpenAI API key

    Returns:
        dict with keys: message, hook, personalization_notes
    """
    if not openai_key:
        logger.warning("[ghost_agency] No OpenAI key configured — using fallback template")
        return _build_fallback(lead)

    platform = lead.get("platform", "email")
    user_prompt = (
        f"Génère un message de prospection pour le prospect suivant:\n"
        f"- Nom: {lead.get('name')}\n"
        f"- Niche: {lead.get('niche')}\n"
        f"- Plateforme: {platform}\n"
        f"- Points de douleur: {lead.get('pain_points')}\n"
        f"- Objectifs: {lead.get('goals')}\n"
        f"- Contexte additionnel: {lead.get('context') or 'Aucun'}\n"
        f"- Contexte de la campagne: {campaign_context or 'Aucun'}\n\n"
        f"Contraintes:\n"
        f"- Le champ 'message' doit faire maximum 300 caractères (pour DM {platform})\n"
        f"- Le champ 'hook' est les 50 premiers caractères accrocheurs du message\n"
        f"- Le champ 'personalization_notes' explique en 1-2 phrases ce qui rend ce message unique pour ce prospect\n"
        f"Réponds UNIQUEMENT avec le JSON."
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 500,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            raw_content = data["choices"][0]["message"]["content"].strip()
            result = json.loads(raw_content)

            # Enforce 300-char cap on message and 50-char cap on hook
            message = str(result.get("message", ""))[:300]
            hook = str(result.get("hook", message[:50]))[:50]
            personalization_notes = str(result.get("personalization_notes", ""))

            return {
                "message": message,
                "hook": hook,
                "personalization_notes": personalization_notes,
            }

    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        logger.error(f"[ghost_agency] OpenAI call failed: {exc} — falling back to template")
        return _build_fallback(lead)
