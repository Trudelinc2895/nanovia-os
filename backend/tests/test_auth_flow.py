"""Critical auth integration tests."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_auth.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-auth-tests"
os.environ["APP_ENV"] = "development"
os.environ["ALLOWED_ORIGINS_RAW"] = "http://localhost:3000"
os.environ["PUBLIC_WEB_URL"] = "http://localhost:3000"
os.environ["PRIVATE_ADMIN_URL"] = "http://localhost:3020"
os.environ["API_BASE_URL"] = "http://127.0.0.1:8010"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

Path("test_auth.db").unlink(missing_ok=True)

from fastapi.testclient import TestClient

from api.main import app


def test_register_sets_refresh_cookie_and_returns_me():
    email = f"{uuid.uuid4()}@example.com"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Prod Ready"},
        )

        assert register.status_code == 201, register.text
        assert "refresh_token=" in (register.headers.get("set-cookie") or "")

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {register.json()['access_token']}"},
        )

        assert me.status_code == 200, me.text
        assert me.json()["email"] == email


def test_refresh_rotates_refresh_cookie():
    email = f"{uuid.uuid4()}@example.com"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Cookie Rotate"},
        )
        assert register.status_code == 201, register.text

        refreshed = client.post("/api/v1/auth/refresh", json={})

        assert refreshed.status_code == 200, refreshed.text
        assert "refresh_token=" in (refreshed.headers.get("set-cookie") or "")
        assert refreshed.json()["access_token"]


def test_register_login_and_portal_route_exposure():
    email = f"{uuid.uuid4()}@example.com"

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1", "full_name": "Flow Check"},
        )
        assert register.status_code == 201, register.text

        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password1"},
        )
        assert login.status_code == 200, login.text
        assert login.json()["access_token"]

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert me.status_code == 200, me.text
        assert me.json()["email"] == email

        portal = client.post("/api/v1/billing/portal-session")
        assert portal.status_code == 401, portal.text


def test_public_entrypoint_health_exposed():
    with TestClient(app) as client:
        resp = client.get("/api/v1/health/public-entrypoint")
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["raw_ip_supported_for_login"] is False
        assert payload["canonical_web_url"].startswith("https://")
