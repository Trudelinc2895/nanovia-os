"""pytest configuration for backend tests."""
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-chars-long-for-testing")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("ALLOWED_ORIGINS_RAW", "http://localhost:3000")
os.environ.setdefault("PUBLIC_WEB_URL", "http://localhost:3000")
os.environ.setdefault("PRIVATE_ADMIN_URL", "http://localhost:3020")
os.environ.setdefault("API_BASE_URL", "http://127.0.0.1:8010")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

def _auth_headers(*, user_id: str, workspace_id: str, tenant_id: str | None = None, is_admin: bool = False, admin_key: str | None = None) -> dict[str, str]:
    from api.core.security import create_access_token

    token = create_access_token(
        user_id,
        extra={
            "plan": "pro",
            "workspace_id": workspace_id,
            "tenant_id": tenant_id or workspace_id,
            "is_admin": is_admin,
        },
    )
    headers = {"Authorization": f"Bearer {token}"}
    if admin_key:
        headers["X-Nanovia-Admin-Key"] = admin_key
    return headers


@pytest.fixture()
def ai_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from api.config import settings
    from api.routers import ai as ai_router
    from api.services import ai_service, sandbox_service

    monkeypatch.setattr(ai_service, "PROMPTS_DIR", tmp_path / "packages" / "ai" / "prompts")
    monkeypatch.setattr(ai_service, "POLICIES_DIR", tmp_path / "packages" / "ai" / "policies")
    monkeypatch.setattr(ai_service, "SCHEMAS_DIR", tmp_path / "packages" / "ai" / "schemas")
    monkeypatch.setattr(ai_service, "AI_DATA_DIR", tmp_path / "data" / "ai")
    monkeypatch.setattr(ai_service, "MEMORY_ROOT", tmp_path / "data" / "memory")
    monkeypatch.setattr(ai_service, "AUDIT_LOG_PATH", tmp_path / "data" / "audit" / "ai-audit.jsonl")
    monkeypatch.setattr(ai_service, "CONVERSATIONS_PATH", tmp_path / "data" / "ai" / "conversations.json")
    monkeypatch.setattr(ai_service, "USAGE_EVENTS_PATH", tmp_path / "data" / "ai" / "usage-events.json")
    monkeypatch.setattr(ai_service, "LEARNING_EVENTS_PATH", tmp_path / "data" / "ai" / "learning-events.json")
    monkeypatch.setattr(ai_service, "PROMPT_GOVERNANCE_PATH", tmp_path / "data" / "ai" / "prompt-governance.json")
    monkeypatch.setattr(ai_service, "TENANT_PROFILES_PATH", tmp_path / "data" / "ai" / "tenant-profiles.json")

    monkeypatch.setattr(sandbox_service, "WORKSPACES_PATH", tmp_path / "data" / "sandbox" / "workspaces.json")
    monkeypatch.setattr(sandbox_service, "RUNTIME_STATE_PATH", tmp_path / "data" / "sandbox" / "runtime-state.json")
    monkeypatch.setattr(sandbox_service, "CREDIT_LEDGER_PATH", tmp_path / "data" / "sandbox" / "credit-ledger.json")
    monkeypatch.setattr(sandbox_service, "USAGE_EVENTS_PATH", tmp_path / "data" / "sandbox" / "usage-events.json")
    monkeypatch.setattr(sandbox_service, "AUDIT_LOG_PATH", tmp_path / "data" / "audit" / "sandbox-audit.jsonl")
    monkeypatch.setattr(sandbox_service, "MEMORY_PATH", tmp_path / "data" / "memory" / "sandbox-memory.json")
    monkeypatch.setattr(sandbox_service, "SUMMARIES_PATH", tmp_path / "data" / "memory" / "summaries.json")
    monkeypatch.setattr(sandbox_service, "PROFILE_PATH", tmp_path / "data" / "memory" / "user-profile.json")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "", raising=False)
    monkeypatch.setattr(settings, "STRIPE_PUBLIC_KEY", "", raising=False)
    monkeypatch.setattr(settings, "AI_ADMIN_API_KEY", "test-admin-key", raising=False)

    ai_service.ensure_runtime_layout()
    app = FastAPI()
    app.include_router(ai_router.router)
    return TestClient(app)


@pytest.fixture()
def tenant_auth_headers():
    return lambda *, user_id="tenant-user", workspace_id="sandbox_workspace", tenant_id=None: _auth_headers(
        user_id=user_id,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
    )


@pytest.fixture()
def admin_auth_headers():
    return lambda *, user_id="owner", workspace_id="sandbox_workspace", tenant_id=None: _auth_headers(
        user_id=user_id,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        is_admin=True,
        admin_key="test-admin-key",
    )
