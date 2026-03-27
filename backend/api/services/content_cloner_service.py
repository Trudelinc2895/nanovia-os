"""
backend/api/services/content_cloner_service.py — Module 2 Content Cloner AI service
"""
from __future__ import annotations

import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Tu es un expert en marketing de contenu viral qui maîtrise parfaitement tous les formats de contenu digital : Twitter/X, LinkedIn, Instagram, newsletter et scripts vidéo.

Tu reçois un contenu source et tu dois le réécrire dans 5 formats différents optimisés pour chaque plateforme.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après, avec exactement ces 5 clés :
- tweet : max 280 caractères, hook fort dès le début, 2-3 hashtags pertinents
- linkedin : 800-1500 caractères, storytelling engageant, appel à l'action clair, emojis stratégiques
- instagram : caption max 150 caractères accrocheur + exactement 5 hashtags pertinents séparés par des espaces
- newsletter : intro percutante de 200-400 caractères suivie d'un corps développé
- video_script : structure en 3 parties : hook (5 secondes) + corps (60 secondes) + CTA (5 secondes)

Format JSON attendu :
{
  "tweet": "...",
  "linkedin": "...",
  "instagram": "...",
  "newsletter": "...",
  "video_script": "..."
}"""

_PLACEHOLDER_FORMATS = {
    "tweet": "⚡ Contenu en cours de génération... Réessaie dans quelques instants. #marketing #contenu",
    "linkedin": "🚀 Nous travaillons à transformer ce contenu pour LinkedIn. Revenez bientôt pour découvrir une version optimisée avec storytelling et appel à l'action.",
    "instagram": "✨ Contenu Instagram bientôt disponible ! #contenu #marketing #creation #digital #soon",
    "newsletter": "**À venir** — Intro newsletter\n\nNous préparons une version optimisée de ce contenu pour votre newsletter. Restez à l'écoute.",
    "video_script": "**HOOK (5s):** [Contenu temporairement indisponible]\n\n**CORPS (60s):** [Script en cours de génération]\n\n**CTA (5s):** [Appel à l'action bientôt disponible]",
}


def _extract_json(text: str) -> dict:
    """Robustly extract a JSON object from an LLM response string."""
    text = text.strip()

    # Direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    fenced = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    fenced = re.sub(r"\s*```$", "", fenced, flags=re.MULTILINE).strip()
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass

    # Find first {...} block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("No valid JSON object found in LLM response")


def _build_user_message(original: str, niche: str | None) -> str:
    niche_hint = f"\nNiche / secteur cible : {niche}" if niche else ""
    return f"Contenu source à transformer :{niche_hint}\n\n{original}"


async def clone_content(
    original: str,
    niche: str | None,
    openai_key: str,
) -> dict:
    """
    Call OpenAI gpt-4o-mini once and return all 5 content formats as a dict.
    Keys: tweet, linkedin, instagram, newsletter, video_script
    Falls back to placeholder formats on any error.
    """
    if not openai_key:
        logger.warning("[content_cloner] No OpenAI key configured — returning placeholders")
        return dict(_PLACEHOLDER_FORMATS)

    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(original, niche)},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
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

        raw_content: str = data["choices"][0]["message"]["content"]
        formats = _extract_json(raw_content)

        # Ensure all required keys are present; fill missing ones with placeholders
        required_keys = {"tweet", "linkedin", "instagram", "newsletter", "video_script"}
        result = {}
        for key in required_keys:
            result[key] = str(formats.get(key) or _PLACEHOLDER_FORMATS[key])

        logger.info("[content_cloner] Successfully generated all 5 formats")
        return result

    except httpx.HTTPStatusError as exc:
        logger.error(f"[content_cloner] OpenAI HTTP error {exc.response.status_code}: {exc.response.text[:200]}")
    except Exception as exc:
        logger.error(f"[content_cloner] Unexpected error: {exc}")

    return dict(_PLACEHOLDER_FORMATS)
