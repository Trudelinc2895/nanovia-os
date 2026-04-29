"""
Unit tests for GET and PUT /api/v1/admin/branding.
Uses mocked DB and admin user — no real DB required.
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@nanovia.ca"
    user.is_admin = True
    return user


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.headers = {"user-agent": "pytest"}
    return req


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


# ─── GET /admin/branding ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_branding_returns_defaults_when_no_row(admin_user, mock_db):
    """GET returns default empty BrandingResponse when no row exists."""
    from api.routers.branding import get_branding, BrandingResponse

    mock_db.execute.return_value = _scalar_result(None)

    result = await get_branding(_admin=admin_user, db=mock_db)

    assert isinstance(result, BrandingResponse)
    assert result.workspace_id == "platform"
    assert result.company_name is None
    assert result.logo_url is None


@pytest.mark.asyncio
async def test_get_branding_returns_existing_row(admin_user, mock_db):
    """GET returns values from the existing DB row."""
    from api.routers.branding import get_branding
    from api.models.branding import Branding

    row = MagicMock(spec=Branding)
    row.workspace_id = "platform"
    row.company_name = "Acme Corp"
    row.logo_url = "https://example.com/logo.png"
    row.primary_color = "#7C3AED"
    row.accent_color = "#4F46E5"
    row.support_email = "support@acme.com"
    row.custom_domain = "acme.nanovia.ca"

    mock_db.execute.return_value = _scalar_result(row)

    result = await get_branding(_admin=admin_user, db=mock_db)

    assert result.company_name == "Acme Corp"
    assert result.primary_color == "#7C3AED"
    assert result.support_email == "support@acme.com"


# ─── PUT /admin/branding ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_put_branding_updates_existing_row(admin_user, mock_db, mock_request):
    """PUT updates and returns the updated BrandingResponse."""
    from api.routers.branding import update_branding, BrandingUpdate
    from api.models.branding import Branding

    row = MagicMock(spec=Branding)
    row.workspace_id = "platform"
    row.company_name = "Old Name"
    row.logo_url = None
    row.primary_color = None
    row.accent_color = None
    row.support_email = None
    row.custom_domain = None

    mock_db.execute.return_value = _scalar_result(row)

    async def fake_refresh(obj):
        obj.company_name = "New Name"
        obj.primary_color = "#FF5500"

    mock_db.refresh.side_effect = fake_refresh

    body = BrandingUpdate(company_name="New Name", primary_color="#FF5500")
    result = await update_branding(body=body, request=mock_request, _admin=admin_user, db=mock_db)

    mock_db.commit.assert_called_once()
    assert row.company_name == "New Name"
    assert row.primary_color == "#FF5500"


@pytest.mark.asyncio
async def test_put_branding_creates_row_when_none_exists(admin_user, mock_db, mock_request):
    """PUT creates a new row if none exists."""
    from api.routers.branding import update_branding, BrandingUpdate
    from api.models.branding import Branding

    mock_db.execute.return_value = _scalar_result(None)

    new_row = MagicMock(spec=Branding)
    new_row.workspace_id = "platform"
    new_row.company_name = "Brand New"
    new_row.logo_url = None
    new_row.primary_color = "#7C3AED"
    new_row.accent_color = None
    new_row.support_email = None
    new_row.custom_domain = None

    async def fake_refresh(obj):
        obj.company_name = "Brand New"
        obj.primary_color = "#7C3AED"

    mock_db.refresh.side_effect = fake_refresh

    body = BrandingUpdate(company_name="Brand New", primary_color="#7C3AED")
    await update_branding(body=body, request=mock_request, _admin=admin_user, db=mock_db)

    mock_db.add.assert_called()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_put_branding_writes_audit_log(admin_user, mock_db, mock_request):
    """PUT must add an AuditLog entry."""
    from api.routers.branding import update_branding, BrandingUpdate
    from api.models.branding import Branding
    from api.models.audit import AuditLog

    row = MagicMock(spec=Branding)
    row.workspace_id = "platform"
    row.company_name = None
    row.logo_url = None
    row.primary_color = None
    row.accent_color = None
    row.support_email = None
    row.custom_domain = None
    mock_db.execute.return_value = _scalar_result(row)
    mock_db.refresh.side_effect = AsyncMock()

    body = BrandingUpdate(company_name="Test")
    await update_branding(body=body, request=mock_request, _admin=admin_user, db=mock_db)

    added_objects = [call.args[0] for call in mock_db.add.call_args_list]
    audit_entries = [o for o in added_objects if isinstance(o, AuditLog)]
    assert len(audit_entries) == 1
    assert audit_entries[0].action == "branding.updated"


@pytest.mark.asyncio
async def test_put_branding_rejects_invalid_color(admin_user, mock_db, mock_request):
    """PUT rejects invalid hex color codes."""
    from pydantic import ValidationError
    from api.routers.branding import BrandingUpdate

    with pytest.raises(ValidationError):
        BrandingUpdate(primary_color="red")

    with pytest.raises(ValidationError):
        BrandingUpdate(primary_color="GGGGGG")
