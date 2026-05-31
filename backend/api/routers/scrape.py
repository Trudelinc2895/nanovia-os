from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.config import settings
from api.core.deps import OptionalUser, get_db
from api.models.user import User
from api.scraping.models import ScrapeMode, ScrapeRequest
from api.scraping.service import enqueue_scrape, get_scrape_job, legacy_scrape_once, scrape_once

router = APIRouter()


async def _require_scraping_access(
    request: Request,
    user: OptionalUser,
    db: Annotated[object, Depends(get_db)],
) -> User | None:
    """Gate scraping access.

    - SCRAPING_REQUIRE_AUTH=false → anonymous allowed, no plan check
    - SCRAPING_REQUIRE_AUTH=true  → valid JWT + scraping feature required
    """
    if not settings.SCRAPING_REQUIRE_AUTH:
        return user  # anonymous OK when auth not required

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization required for scraping",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from api.core.monetization import canUseFeature

    if not await canUseFeature(str(user.id), "scraping", db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le scraping n'est pas disponible dans ton plan actuel. Upgrade requis.",
        )
    return user


def _resolve_client_id(
    request: Request,
    explicit_client_id: str | None,
    user: User | None,
) -> str:
    if explicit_client_id:
        return explicit_client_id.strip()[:128]
    if user:
        return str(user.id)[:36]
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:30]
    if request.client and request.client.host:
        return request.client.host
    return "anonymous"


@router.get("/scrape")
async def scrape(
    request: Request,
    url: str = Query(..., min_length=4, max_length=4096),
    mode: ScrapeMode | None = Query(default=None),
    render_js: bool = Query(default=False),
    force_refresh: bool = Query(default=False),
    client_id: str | None = Query(default=None, max_length=128),
    user: Annotated[User | None, Depends(_require_scraping_access)] = None,
):
    if not settings.SCRAPING_ENABLED:
        raise HTTPException(status_code=404, detail="Scraping is disabled")

    req = ScrapeRequest(
        url=url,
        mode=mode or settings.SCRAPING_MODE_DEFAULT,
        render_js=render_js,
        force_refresh=force_refresh,
        client_id=_resolve_client_id(request, client_id, user),
    )

    if not settings.SCRAPING_PROXY_LAYER_ENABLED:
        if req.mode == "async":
            raise HTTPException(status_code=503, detail="Asynchronous scraping requires ENABLE_SCRAPE_PROXY=true")
        return await legacy_scrape_once(req)

    if req.mode == "async":
        try:
            return await enqueue_scrape(req)
        except HTTPException as exc:
            if not settings.SCRAPING_FALLBACK_DIRECT_ENABLED or exc.status_code != 503:
                raise
            sync_req = req.model_copy(update={"mode": "sync"})
            return await scrape_once(sync_req)

    return await scrape_once(req)


@router.get("/scrape/jobs/{job_id}")
async def scrape_job(job_id: str):
    if not settings.SCRAPING_ENABLED:
        raise HTTPException(status_code=404, detail="Scraping is disabled")
    return await get_scrape_job(job_id)
