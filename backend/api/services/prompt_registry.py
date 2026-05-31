from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status

from api.services import ai_service

_SAFE_PROMPT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}\.md$")

DEFAULT_PROMPTS: dict[str, str] = {
    "master_prompt.md": (
        "Tu es l'IA maitre Nanovia, controlee par le super admin. "
        "Tu analyses des agregats, améliores prompts, surveilles couts et ne partages jamais les donnees brutes des tenants."
    ),
    "tenant_base_prompt.md": (
        "Tu es l'IA personnalisee d'un tenant Nanovia. "
        "Tu respectes le plan, les modules autorises, la memoire privee et les limites de credits."
    ),
    "support_prompt.md": "Tu aides a repondre au support sans exposer de donnees sensibles.",
    "billing_prompt.md": "Tu aides au billing Nanovia en gardant la rentabilite et les quotas.",
    "devops_prompt.md": "Tu aides aux operations DevOps Nanovia sans action destructive sans confirmation.",
}


def _resolve_prompt_path(prompt_name: str):
    cleaned = (prompt_name or "").strip()
    if not _SAFE_PROMPT_NAME.fullmatch(cleaned):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsafe prompt_name.")
    path = (ai_service.PROMPTS_DIR / cleaned).resolve()
    prompts_root = ai_service.PROMPTS_DIR.resolve()
    if prompts_root not in path.parents:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Prompt path escapes prompt registry.")
    return cleaned, path


def load_prompt(prompt_name: str) -> str:
    prompt_name, path = _resolve_prompt_path(prompt_name)
    default = DEFAULT_PROMPTS.get(prompt_name, "")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default + "\n", encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def update_prompt(prompt_name: str, content: str, *, actor: str) -> dict[str, Any]:
    prompt_name, path = _resolve_prompt_path(prompt_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    event = {
        "id": f"prompt_{actor}_{prompt_name}",
        "prompt_name": prompt_name,
        "actor": actor,
        "updated_at": ai_service.utcnow(),
        "length": len(content),
    }
    ai_service.record_prompt_update(event)
    return event
