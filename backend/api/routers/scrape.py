from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.config import settings
from api.scraping.models import ScrapeMode, ScrapeRequest
from api.scraping.service import enqueue_scrape, get_scrape_job, scrape_once

router = APIRouter()


def _resolve_client_id(request: Request, explicit_client_id: str | None) -> str:
    if explicit_client_id:
        return explicit_client_id.strip()[:128]

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
):
    if not settings.SCRAPING_ENABLED:
        raise HTTPException(status_code=404, detail="Scraping is disabled")

    if settings.SCRAPING_REQUIRE_AUTH and not request.headers.get("authorization"):
        raise HTTPException(status_code=401, detail="Authorization required")

    req = ScrapeRequest(
        url=url,
        mode=mode or settings.SCRAPING_MODE_DEFAULT,
        render_js=render_js,
        force_refresh=force_refresh,
        client_id=_resolve_client_id(request, client_id),
    )

    if req.mode == "async":
        return await enqueue_scrape(req)

    return await scrape_once(req)


@router.get("/scrape/jobs/{job_id}")
async def scrape_job(job_id: str):
    if not settings.SCRAPING_ENABLED:
        raise HTTPException(status_code=404, detail="Scraping is disabled")
    return await get_scrape_job(job_id)
