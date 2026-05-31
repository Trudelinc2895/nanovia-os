from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ScrapeMode = Literal["sync", "async"]
JobStatus = Literal["queued", "processing", "done", "failed"]


class ScrapeResult(BaseModel):
    url: str
    normalized_url: str
    domain: str
    status_code: int
    content_type: str
    body: str
    fetched_via: Literal["http", "playwright"] = "http"
    cache_hit: bool = False
    redirect_count: int = 0
    response_bytes: int = 0
    used_proxy: bool = False


class ScrapeJobEnqueueResponse(BaseModel):
    job_id: str
    status: JobStatus
    queued: bool = True


class ScrapeJobState(BaseModel):
    job_id: str
    status: JobStatus
    created_at: int
    updated_at: int
    attempts: int = 0
    normalized_url: str
    result: ScrapeResult | None = None
    error: str | None = None


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=4, max_length=4096)
    mode: ScrapeMode = "sync"
    render_js: bool = False
    force_refresh: bool = False
    client_id: str | None = Field(default=None, max_length=128)
