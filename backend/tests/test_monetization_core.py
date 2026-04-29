"""Unit tests for the Nanovia central monetization core."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_active_plan_uses_workspace_bridge():
    from api.core.monetization import getActivePlan

    workspace_id = str(uuid.uuid4())
    owner = type("Owner", (), {"id": workspace_id})()

    with (
        patch(
            "api.core.monetization.billing_service.get_workspace_owner",
            new=AsyncMock(return_value=owner),
        ),
        patch(
            "api.services.entitlements_service.get_effective_plan",
            new=AsyncMock(return_value="pro"),
        ),
    ):
        plan = await getActivePlan(workspace_id, AsyncMock())

    assert plan == "pro"


@pytest.mark.asyncio
async def test_get_entitlements_adds_workspace_metadata():
    from api.core.monetization import getEntitlements

    workspace_id = str(uuid.uuid4())
    owner = type("Owner", (), {"id": workspace_id})()
    entitlements = {"plan": "business", "features_enabled": {"white_label": True}, "credits": 12}

    with (
        patch(
            "api.core.monetization.entitlements_service.get_workspace_owner",
            new=AsyncMock(return_value=owner),
        ),
        patch(
            "api.services.entitlements_service.get_entitlements",
            new=AsyncMock(return_value=entitlements),
        ),
    ):
        result = await getEntitlements(workspace_id, AsyncMock())

    assert result["workspace_id"] == workspace_id
    assert result["workspace_mode"] == "compat_user_owner"
    assert result["plan"] == "business"


@pytest.mark.asyncio
async def test_get_entitlements_uses_ledger_balance_for_credit_reads():
    from api.services.entitlements_service import get_entitlements

    user = type("UserLike", (), {"id": uuid.uuid4()})()
    legacy_entitlements = {
        "plan": "pro",
        "features_enabled": {"automation": True, "overage_allowed": True},
        "credits": 0,
    }

    with (
        patch(
            "api.services.billing_service.get_active_subscription",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.services.usage_service.get_monthly_usage",
            new=AsyncMock(return_value={"messages_count": 0}),
        ),
        patch(
            "api.services.billing_service.compute_entitlements",
            return_value=legacy_entitlements.copy(),
        ),
        patch(
            "api.services.credit_service.get_authoritative_credit_balance",
            new=AsyncMock(return_value=9),
        ),
    ):
        result = await get_entitlements(user, AsyncMock())

    assert result["credits"] == 9


@pytest.mark.asyncio
async def test_can_use_feature_reads_centralized_entitlements():
    from api.core.monetization import canUseFeature

    active_workspace = type("Workspace", (), {"status": "active"})()

    with (
        patch(
            "api.core.monetization.entitlements_service.get_workspace",
            new=AsyncMock(return_value=active_workspace),
        ),
        patch(
            "api.core.monetization.entitlements_service.get_entitlements",
            new=AsyncMock(return_value={"status": "active", "features_enabled": {"automation": True}}),
        ),
        patch(
            "api.core.monetization.usage_metering_service.get_usage_snapshot",
            new=AsyncMock(return_value={"quota": {"ai_messages": {"exceeded": False}}}),
        ),
    ):
        allowed = await canUseFeature(str(uuid.uuid4()), "automation", AsyncMock())

    assert allowed is True


@pytest.mark.asyncio
async def test_can_use_feature_blocks_inactive_workspace():
    from api.core.monetization import canUseFeature

    blocked_workspace = type("Workspace", (), {"status": "blocked"})()

    with patch(
        "api.core.monetization.entitlements_service.get_workspace",
        new=AsyncMock(return_value=blocked_workspace),
    ):
        allowed = await canUseFeature(str(uuid.uuid4()), "automation", AsyncMock())

    assert allowed is False


@pytest.mark.asyncio
async def test_can_use_feature_blocks_metered_feature_without_overage_capacity():
    from api.core.monetization import canUseFeature

    active_workspace = type("Workspace", (), {"status": "active"})()

    with (
        patch(
            "api.core.monetization.entitlements_service.get_workspace",
            new=AsyncMock(return_value=active_workspace),
        ),
        patch(
            "api.core.monetization.entitlements_service.get_entitlements",
            new=AsyncMock(return_value={"status": "active", "features_enabled": {"automation": True}}),
        ),
        patch(
            "api.core.monetization.usage_metering_service.get_usage_snapshot",
            new=AsyncMock(return_value={"quota": {"ai_messages": {"exceeded": True}}}),
        ),
        patch(
            "api.core.monetization.billing_service.resolve_overage_policy",
            new=AsyncMock(return_value={"action": "block_no_credits"}),
        ),
    ):
        allowed = await canUseFeature(str(uuid.uuid4()), "automation", AsyncMock())

    assert allowed is False


@pytest.mark.asyncio
async def test_consume_credits_returns_structured_result():
    from api.core.monetization import consumeCredits

    workspace_id = str(uuid.uuid4())
    owner_before = type("Owner", (), {"credits": 5})()
    owner_after = type("Owner", (), {"credits": 3})()
    active_workspace = type("Workspace", (), {"status": "active"})()

    with (
        patch(
            "api.core.monetization.credits_service.get_workspace",
            new=AsyncMock(return_value=active_workspace),
        ),
        patch(
            "api.core.monetization.credits_service.get_workspace_owner",
            new=AsyncMock(side_effect=[owner_before, owner_after]),
        ),
        patch(
            "api.core.monetization.credits_service.deduct_credits",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await consumeCredits(
            workspace_id,
            "ai_usage",
            2,
            AsyncMock(),
            actorId="actor-1",
            idempotency_key="idem-1",
        )

    assert result == {
        "workspace_id": workspace_id,
        "usage_type": "ai_usage",
        "quantity": 2,
        "allowed": True,
        "balance_after": 3,
        "reason": "credits_consumed",
    }


def test_build_usage_event_normalizes_required_fields():
    from api.core.monetization.usage_metering_service import build_usage_event

    event = build_usage_event(
        workspace_id="ws-1",
        usage_type="api_call",
        quantity=4,
        actor_id="user-1",
        request_id="req-1",
        idempotency_key="idem-1",
        cost="1.25",
    )

    assert event["type"] == "api_call"
    assert event["quantity"] == 4
    assert event["cost"] == "1.25"
    assert event["workspaceId"] == "ws-1"
    assert event["actorId"] == "user-1"
    assert event["requestId"] == "req-1"
    assert event["idempotency_key"] == "idem-1"
    assert "timestamp" in event


@pytest.mark.asyncio
async def test_handle_stripe_webhook_short_circuits_duplicates():
    from api.core.monetization.webhook_handler_service import handle_stripe_webhook

    with patch(
        "api.core.monetization.webhook_handler_service.claim_webhook_event",
        new=AsyncMock(return_value=False),
    ):
        result = await handle_stripe_webhook("evt_1", "invoice.payment_failed", {}, AsyncMock())

    assert result == {
        "event_id": "evt_1",
        "event_type": "invoice.payment_failed",
        "status": "duplicate",
    }


@pytest.mark.asyncio
async def test_ensure_owner_workspace_creates_workspace_and_owner_member():
    from api.core.monetization._workspace import ensure_owner_workspace
    from api.models.workspace_billing import CreditBalance, Member, Workspace

    user_id = uuid.uuid4()
    user = type(
        "UserLike",
        (),
        {
            "id": user_id,
            "email": "owner@example.com",
            "full_name": "Owner Name",
            "plan": "pro",
            "created_at": object(),
        },
    )()

    no_row = MagicMock()
    no_row.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[no_row, no_row, no_row])
    db.add = MagicMock()
    db.flush = AsyncMock()

    workspace = await ensure_owner_workspace(user, db)

    added = [call.args[0] for call in db.add.call_args_list]
    assert isinstance(workspace, Workspace)
    assert workspace.id == user_id
    assert workspace.owner_user_id == user_id
    assert workspace.active_plan_key == "pro"
    assert any(isinstance(item, Workspace) for item in added)
    owner_member = next(item for item in added if isinstance(item, Member))
    credit_balance = next(item for item in added if isinstance(item, CreditBalance))
    assert owner_member.workspace_id == user_id
    assert owner_member.user_id == user_id
    assert owner_member.role == "owner"
    assert owner_member.status == "active"
    assert credit_balance.workspace_id == user_id
    assert credit_balance.balance == 0
