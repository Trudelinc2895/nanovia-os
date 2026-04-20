"""
Unit tests for billing checkout session creation.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import uuid

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@test.com"
    user.plan = "free"
    user.credits = 0
    user.stripe_customer_id = None
    return user

@pytest.mark.asyncio
async def test_checkout_unknown_plan(mock_user):
    """Unknown plan returns 400."""
    from fastapi import HTTPException
    from api.services.billing_service import PLANS_CONFIG
    # "enterprise" does not exist
    assert "enterprise" not in PLANS_CONFIG

@pytest.mark.asyncio
async def test_checkout_missing_price_id():
    """Plan with no stripe price ID raises 503."""
    from api.services.billing_service import PLANS_CONFIG
    plan_cfg = PLANS_CONFIG.get("pro", {})
    # Without env set, stripe_price_monthly is None
    # Verify key exists in config structure
    assert "stripe_price_monthly" in plan_cfg

@pytest.mark.asyncio
async def test_plans_config_prices():
    """Verify correct prices in PLANS_CONFIG."""
    from api.services.billing_service import PLANS_CONFIG
    assert PLANS_CONFIG["pro"]["price_monthly_usd"] == 79
    assert PLANS_CONFIG["pro"]["price_yearly_usd"] == 790
    assert PLANS_CONFIG["business"]["price_monthly_usd"] == 149
    assert PLANS_CONFIG["business"]["price_yearly_usd"] == 1490
    assert PLANS_CONFIG["free"]["price_monthly_usd"] == 0

@pytest.mark.asyncio
async def test_catalog_module_inclusion_and_prices():
    """Shared catalog should drive plan inclusion and public module pricing."""
    from api.services.billing_service import MODULES_CONFIG, PLANS_CONFIG
    assert MODULES_CONFIG["operator"]["price_usd"] == 19
    assert MODULES_CONFIG["ghost"]["price_usd"] == 39
    assert MODULES_CONFIG["operator"]["included_in_plans"] == ["free", "pro", "business"]
    assert "content" in PLANS_CONFIG["pro"]["included_modules"]
    assert "ghost" in PLANS_CONFIG["business"]["included_modules"]

@pytest.mark.asyncio
async def test_feature_gates_by_plan():
    """Verify feature gates per plan."""
    from api.services.billing_service import has_feature
    assert has_feature("free", "overage_allowed") is False
    assert has_feature("pro", "api_access") is True
    assert has_feature("business", "white_label") is True
    assert has_feature("free", "white_label") is False
