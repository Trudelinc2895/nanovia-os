"""Focused tests for mobile entitlement gating."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from fastapi import HTTPException

os.environ["ADMIN_ALLOWED_IPS_RAW"] = "203.0.113.10/32"

from api.routers import mobile


def _make_user(plan: str = "free", *, is_admin: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        plan=plan,
        credits=0,
        is_admin=is_admin,
    )


@pytest.mark.asyncio
async def test_modules_catalog_uses_canonical_included_plans(monkeypatch):
    user = _make_user()
    db = AsyncMock()

    async def _fake_has_module_access(_user, slug: str, _db) -> bool:
        return slug == "operator"

    monkeypatch.setattr(mobile, "has_module_access", _fake_has_module_access)

    modules = await mobile.get_modules_catalog(user, db)

    ghost = next(module for module in modules if module["key"] == "ghost_agency")
    operator = next(module for module in modules if module["key"] == "operator")

    assert ghost["slug"] == "ghost"
    assert ghost["entitlements_required"] == ["business"]
    assert ghost["is_available"] is False
    assert operator["slug"] == "operator"
    assert operator["entitlements_required"] == ["free", "pro", "business"]
    assert operator["is_available"] is True


@pytest.mark.asyncio
async def test_vip_overview_blocks_stale_paid_plan_without_active_subscription(monkeypatch):
    user = _make_user(plan="pro")
    db = AsyncMock()

    async def _no_subscription(*_args, **_kwargs):
        return None

    monkeypatch.setattr(mobile, "get_active_subscription", _no_subscription)

    with pytest.raises(HTTPException) as exc_info:
        await mobile.get_vip_overview(user, db)

    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == "Active subscription required."


@pytest.mark.asyncio
async def test_vip_overview_allows_active_paid_subscription(monkeypatch):
    user = _make_user(plan="business")
    db = AsyncMock()
    sub = SimpleNamespace(
        status="active",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=7),
        stripe_subscription_id="sub_123",
        cancel_at_period_end=False,
        billing_interval="month",
    )

    async def _active_subscription(*_args, **_kwargs):
        return sub

    async def _monthly_usage(*_args, **_kwargs):
        return {"messages_count": 12, "tokens_total": 345, "cost_usd_total": 1.23}

    monkeypatch.setattr(mobile, "get_active_subscription", _active_subscription)
    monkeypatch.setattr("api.services.usage_service.get_monthly_usage", _monthly_usage)

    payload = await mobile.get_vip_overview(user, db)

    assert payload["subscription"]["status"] == "active"
    assert payload["kpis"][0]["value"] == "BUSINESS"


@pytest.mark.asyncio
async def test_vip_overview_allows_past_due_subscription_during_recovery_window(monkeypatch):
    user = _make_user(plan="pro")
    db = AsyncMock()
    sub = SimpleNamespace(
        status="past_due",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=2),
        stripe_subscription_id="sub_recovery",
        cancel_at_period_end=False,
        billing_interval="month",
    )

    async def _recovery_subscription(*_args, **_kwargs):
        return sub

    async def _monthly_usage(*_args, **_kwargs):
        return {"messages_count": 3, "tokens_total": 120, "cost_usd_total": 0.42}

    monkeypatch.setattr(mobile, "get_active_subscription", _recovery_subscription)
    monkeypatch.setattr("api.services.usage_service.get_monthly_usage", _monthly_usage)

    payload = await mobile.get_vip_overview(user, db)

    assert payload["subscription"]["status"] == "past_due"
    assert payload["kpis"][0]["value"] == "PRO"
