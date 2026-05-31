from __future__ import annotations

import logging
from typing import Literal

import httpx
from fastapi import HTTPException, Request, status

from api.config import settings
from api.core.deps import _request_client_ip

logger = logging.getLogger(__name__)

TurnstileSurface = Literal["login", "register", "contact", "billing"]

_SURFACE_FLAGS: dict[TurnstileSurface, str] = {
    "login": "TURNSTILE_PROTECT_LOGIN",
    "register": "TURNSTILE_PROTECT_REGISTER",
    "contact": "TURNSTILE_PROTECT_CONTACT",
    "billing": "TURNSTILE_PROTECT_BILLING",
}

_SURFACE_ACTIONS: dict[TurnstileSurface, str] = {
    "login": "login",
    "register": "register",
    "contact": "contact",
    "billing": "billing_checkout",
}


def _should_enforce(surface: TurnstileSurface) -> bool:
    if not settings.TURNSTILE_ENABLED:
        return False
    return bool(getattr(settings, _SURFACE_FLAGS[surface], False))


def _client_ip(request: Request) -> str:
    return _request_client_ip(request) or ""


async def enforce_turnstile(
    request: Request,
    token: str | None,
    *,
    surface: TurnstileSurface,
) -> None:
    if not _should_enforce(surface):
        return

    if not settings.TURNSTILE_SECRET_KEY:
        logger.error("[turnstile] TURNSTILE_SECRET_KEY missing while %s protection is enabled", surface)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La protection anti-bot n'est pas configurée.",
        )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Validation anti-bot requise.",
        )

    payload = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }
    remote_ip = _client_ip(request)
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.TURNSTILE_SITEVERIFY_URL, data=payload)
        response.raise_for_status()
        verification = response.json()
    except httpx.HTTPError as exc:
        logger.warning("[turnstile] verification request failed surface=%s ip=%s error=%s", surface, remote_ip, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La verification anti-bot est temporairement indisponible.",
        ) from exc

    if not verification.get("success"):
        logger.info(
            "[turnstile] verification failed surface=%s ip=%s errors=%s",
            surface,
            remote_ip,
            verification.get("error-codes", []),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Validation anti-bot invalide. Réessaie.",
        )

    expected_action = _SURFACE_ACTIONS[surface]
    actual_action = str(verification.get("action") or "")
    if actual_action != expected_action:
        logger.warning(
            "[turnstile] unexpected action surface=%s expected=%s actual=%s",
            surface,
            expected_action,
            actual_action,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le jeton anti-bot ne correspond pas à cette action.",
        )

    hostname = str(verification.get("hostname") or "").lower()
    allowed_hostnames = settings.TURNSTILE_ALLOWED_HOSTNAMES
    if hostname and allowed_hostnames and hostname not in allowed_hostnames:
        logger.warning(
            "[turnstile] unexpected hostname surface=%s hostname=%s allowed=%s",
            surface,
            hostname,
            ",".join(allowed_hostnames),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le jeton anti-bot provient d'un hote non autorisé.",
        )
