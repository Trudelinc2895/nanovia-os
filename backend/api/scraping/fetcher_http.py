from __future__ import annotations

import httpx
from fastapi import HTTPException

from api.config import settings
from api.scraping.security import validate_redirect


def _validate_content_type(content_type_header: str) -> str:
    header = (content_type_header or "").split(";", 1)[0].strip().lower()
    if not header:
        raise HTTPException(status_code=415, detail="Missing content-type")
    if header not in settings.SCRAPING_ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported content-type: {header}")
    return header


async def fetch_http(
    normalized_url: str,
    *,
    proxy: str | None,
    request_headers: dict[str, str],
) -> tuple[int, str, str, int, bool]:
    timeout = httpx.Timeout(settings.SCRAPING_TIMEOUT_SECONDS)
    current_url = normalized_url
    redirect_count = 0

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, proxy=proxy) as client:
        for _ in range(settings.SCRAPING_MAX_REDIRECTS + 1):
            response = await client.get(current_url, headers=request_headers)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "")
                if not location:
                    raise HTTPException(status_code=502, detail="Redirect without location")
                current_url = validate_redirect(current_url, location)
                redirect_count += 1
                continue

            content_type = _validate_content_type(response.headers.get("content-type", ""))
            body_bytes = response.content
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > settings.SCRAPING_MAX_RESPONSE_BYTES:
                        raise HTTPException(status_code=413, detail="Response too large")
                except ValueError:
                    pass
            if len(body_bytes) > settings.SCRAPING_MAX_RESPONSE_BYTES:
                raise HTTPException(status_code=413, detail="Response too large")
            return response.status_code, content_type, body_bytes.decode("utf-8", errors="replace"), redirect_count, bool(proxy)

    raise HTTPException(status_code=508, detail="Too many redirects")

