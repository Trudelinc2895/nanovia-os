"""
backend/api/main.py
KT Monetization OS — FastAPI production entry point
"""
from __future__ import annotations
import time, uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv(".env")

from api.config import settings
from api.database import engine, Base
from api.routers import auth, billing, modules, users, health
# Import models so Base knows about them before create_all
import api.models  # noqa: F401

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    print(f"[startup] {settings.APP_NAME} v{settings.APP_VERSION} env={settings.APP_ENV}")
    # Auto-create tables (idempotent — use Alembic for schema changes in prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[startup] DB tables ready")
    yield
    print("[shutdown] clean exit")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_meta(request: Request, call_next) -> Response:
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.perf_counter()
    response: Response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Response-Time"] = f"{ms:.1f}ms"
    return response


if HAS_PROMETHEUS:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])
app.include_router(modules.router, prefix="/api/v1/modules", tags=["modules"])
