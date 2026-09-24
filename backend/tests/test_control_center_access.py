from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.config import settings
from api.core.deps import get_admin_user, has_control_center_access, is_control_center_owner


def _request(ip: str = "203.0.113.10"):
    return SimpleNamespace(
        url=SimpleNamespace(path="/api/v1/admin/pilot-requests"),
        headers={"x-forwarded-for": ip},
        client=SimpleNamespace(host=ip),
    )


def test_internationalized_email_is_compared_without_crashing(monkeypatch):
    monkeypatch.setattr(settings, "CONTROL_CENTER_OWNER_EMAIL", "Équipe@nanovia.ca")
    owner = SimpleNamespace(email="équipe@nanovia.ca")
    other = SimpleNamespace(email="autre@nanovia.ca")

    assert is_control_center_owner(owner) is True
    assert is_control_center_owner(other) is False


@pytest.mark.asyncio
async def test_configured_owner_is_the_only_human_with_control_center_access(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "CONTROL_CENTER_OWNER_EMAIL", "owner@nanovia.ca")
    owner = SimpleNamespace(email="OWNER@nanovia.ca", is_admin=True, totp_enabled=True)
    other_admin = SimpleNamespace(email="other@nanovia.ca", is_admin=True, totp_enabled=True)

    assert is_control_center_owner(owner) is True
    assert has_control_center_access(owner) is True
    assert has_control_center_access(other_admin) is False
    assert await get_admin_user(owner, _request()) is owner

    with pytest.raises(HTTPException) as denied:
        await get_admin_user(other_admin, _request())
    assert denied.value.status_code == 403
    assert denied.value.detail == "Control center owner approval required"


@pytest.mark.asyncio
async def test_production_control_center_requires_owner_2fa(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "CONTROL_CENTER_OWNER_EMAIL", "owner@nanovia.ca")
    monkeypatch.setattr(settings, "ADMIN_ALLOWED_IPS_RAW", "203.0.113.10/32")
    owner = SimpleNamespace(email="owner@nanovia.ca", is_admin=True, totp_enabled=False)

    with pytest.raises(HTTPException) as denied:
        await get_admin_user(owner, _request())
    assert denied.value.status_code == 403
    assert denied.value.detail == "Owner 2FA required for control center access"

    owner.totp_enabled = True
    assert await get_admin_user(owner, _request()) is owner


@pytest.mark.asyncio
async def test_production_control_center_fails_closed_without_owner_configuration(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "CONTROL_CENTER_OWNER_EMAIL", "")
    admin = SimpleNamespace(email="admin@nanovia.ca", is_admin=True, totp_enabled=True)

    assert has_control_center_access(admin) is False
    with pytest.raises(HTTPException) as denied:
        await get_admin_user(admin, _request())
    assert denied.value.status_code == 503
    assert denied.value.detail == "Control center owner is not configured"
