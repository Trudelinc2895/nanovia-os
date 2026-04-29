"""
Unit tests for list, create, delete /api/v1/modules/custom.
Uses mocked DB and authenticated user — no real DB required.
"""
from __future__ import annotations

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def business_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user@nanovia.ca"
    user.plan = "business"
    return user


@pytest.fixture
def free_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "free@nanovia.ca"
    user.plan = "free"
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


def _scalars_result(values: list):
    inner = MagicMock()
    inner.all.return_value = values
    result = MagicMock()
    result.scalars.return_value = inner
    return result


def _make_module(owner_id, name="Test Module", slug="test-module"):
    from api.models.custom_module import CustomModule
    mod = MagicMock(spec=CustomModule)
    mod.id = uuid.uuid4()
    mod.owner_user_id = owner_id
    mod.name = name
    mod.slug = slug
    mod.description = "A test module"
    mod.prompt_template = "You are a helpful assistant."
    mod.is_active = True
    mod.created_at = datetime.now(timezone.utc)
    return mod


# ─── _require_business ────────────────────────────────────────────────────────

def test_require_business_blocks_free_user(free_user):
    """Free user cannot access custom modules."""
    from api.routers.custom_modules import _require_business

    with pytest.raises(HTTPException) as exc_info:
        _require_business(free_user)
    assert exc_info.value.status_code == 403


def test_require_business_allows_business_user(business_user):
    """Business user passes the gate."""
    from api.routers.custom_modules import _require_business

    _require_business(business_user)  # Should not raise


# ─── GET /modules/custom ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_custom_modules_returns_active_modules(business_user, mock_db):
    """List returns only active modules for the user."""
    from api.routers.custom_modules import list_custom_modules

    mod = _make_module(business_user.id)
    mock_db.execute.return_value = _scalars_result([mod])

    result = await list_custom_modules(user=business_user, db=mock_db)

    assert len(result) == 1
    assert result[0].name == mod.name
    assert result[0].is_active is True


@pytest.mark.asyncio
async def test_list_custom_modules_returns_empty_when_none(business_user, mock_db):
    """List returns empty list when user has no modules."""
    from api.routers.custom_modules import list_custom_modules

    mock_db.execute.return_value = _scalars_result([])

    result = await list_custom_modules(user=business_user, db=mock_db)

    assert result == []


@pytest.mark.asyncio
async def test_list_custom_modules_blocked_for_free_user(free_user, mock_db):
    """Free user gets 403 on list."""
    from api.routers.custom_modules import list_custom_modules

    with pytest.raises(HTTPException) as exc_info:
        await list_custom_modules(user=free_user, db=mock_db)
    assert exc_info.value.status_code == 403


# ─── POST /modules/custom ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_custom_module_success(business_user, mock_db, mock_request):
    """Business user can create a custom module."""
    from api.routers.custom_modules import create_custom_module, CustomModuleCreate

    mock_db.execute.return_value = _scalar_result(None)  # no slug collision

    created_mod = _make_module(business_user.id, "My AI Tool", "my-ai-tool")

    async def fake_refresh(obj):
        obj.id = created_mod.id
        obj.name = created_mod.name
        obj.slug = created_mod.slug
        obj.description = created_mod.description
        obj.prompt_template = created_mod.prompt_template
        obj.is_active = True
        obj.created_at = created_mod.created_at

    mock_db.refresh.side_effect = fake_refresh

    body = CustomModuleCreate(
        name="My AI Tool",
        prompt_template="You are a custom AI assistant for my needs.",
    )

    result = await create_custom_module(body=body, request=mock_request, user=business_user, db=mock_db)

    mock_db.add.assert_called()
    mock_db.commit.assert_called_once()
    assert result.name == "My AI Tool"
    assert result.slug == "my-ai-tool"


@pytest.mark.asyncio
async def test_create_custom_module_blocked_for_free_user(free_user, mock_db, mock_request):
    """Free user gets 403 on create."""
    from api.routers.custom_modules import create_custom_module, CustomModuleCreate

    body = CustomModuleCreate(
        name="My Module",
        prompt_template="You are helpful.",
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_custom_module(body=body, request=mock_request, user=free_user, db=mock_db)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_create_custom_module_writes_audit_log(business_user, mock_db, mock_request):
    """Create must add an AuditLog entry."""
    from api.routers.custom_modules import create_custom_module, CustomModuleCreate
    from api.models.audit import AuditLog

    mock_db.execute.return_value = _scalar_result(None)

    created_mod = _make_module(business_user.id, "Audit Test", "audit-test")

    async def fake_refresh(obj):
        obj.id = created_mod.id
        obj.name = "Audit Test"
        obj.slug = "audit-test"
        obj.description = None
        obj.prompt_template = "Prompt for audit test."
        obj.is_active = True
        obj.created_at = created_mod.created_at

    mock_db.refresh.side_effect = fake_refresh

    body = CustomModuleCreate(name="Audit Test", prompt_template="Prompt for audit test.")
    await create_custom_module(body=body, request=mock_request, user=business_user, db=mock_db)

    added_objects = [call.args[0] for call in mock_db.add.call_args_list]
    audit_entries = [o for o in added_objects if isinstance(o, AuditLog)]
    assert len(audit_entries) == 1
    assert audit_entries[0].action == "custom_module.created"


@pytest.mark.asyncio
async def test_create_custom_module_name_too_short(business_user, mock_db, mock_request):
    """Name below 3 chars raises ValidationError."""
    from pydantic import ValidationError
    from api.routers.custom_modules import CustomModuleCreate

    with pytest.raises(ValidationError):
        CustomModuleCreate(name="AB", prompt_template="Valid prompt here.")


@pytest.mark.asyncio
async def test_create_custom_module_prompt_too_short(business_user, mock_db, mock_request):
    """Prompt below 10 chars raises ValidationError."""
    from pydantic import ValidationError
    from api.routers.custom_modules import CustomModuleCreate

    with pytest.raises(ValidationError):
        CustomModuleCreate(name="Valid Name", prompt_template="Short")


# ─── DELETE /modules/custom/{module_id} ──────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_custom_module_success(business_user, mock_db, mock_request):
    """Delete sets is_active=False on owned module."""
    from api.routers.custom_modules import delete_custom_module

    mod = _make_module(business_user.id)
    mock_db.execute.return_value = _scalar_result(mod)

    await delete_custom_module(
        module_id=str(mod.id),
        request=mock_request,
        user=business_user,
        db=mock_db,
    )

    assert mod.is_active is False
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_custom_module_not_found(business_user, mock_db, mock_request):
    """Delete returns 404 when module doesn't exist."""
    from api.routers.custom_modules import delete_custom_module

    mock_db.execute.return_value = _scalar_result(None)

    with pytest.raises(HTTPException) as exc_info:
        await delete_custom_module(
            module_id=str(uuid.uuid4()),
            request=mock_request,
            user=business_user,
            db=mock_db,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_custom_module_invalid_uuid(business_user, mock_db, mock_request):
    """Delete returns 422 for a non-UUID module_id."""
    from api.routers.custom_modules import delete_custom_module

    with pytest.raises(HTTPException) as exc_info:
        await delete_custom_module(
            module_id="not-a-uuid",
            request=mock_request,
            user=business_user,
            db=mock_db,
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_delete_custom_module_writes_audit_log(business_user, mock_db, mock_request):
    """Delete must add an AuditLog entry."""
    from api.routers.custom_modules import delete_custom_module
    from api.models.audit import AuditLog

    mod = _make_module(business_user.id, "To Delete", "to-delete")
    mock_db.execute.return_value = _scalar_result(mod)

    await delete_custom_module(
        module_id=str(mod.id),
        request=mock_request,
        user=business_user,
        db=mock_db,
    )

    added_objects = [call.args[0] for call in mock_db.add.call_args_list]
    audit_entries = [o for o in added_objects if isinstance(o, AuditLog)]
    assert len(audit_entries) == 1
    assert audit_entries[0].action == "custom_module.deleted"
