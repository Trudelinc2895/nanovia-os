"""Unit tests for the Nanovia central monetization core."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
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

    with (
        patch(
            "api.core.monetization.webhook_handler_service.get_webhook_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.claim_webhook_event",
            new=AsyncMock(return_value="duplicate"),
        ),
    ):
        result = await handle_stripe_webhook("evt_1", "invoice.payment_failed", {}, AsyncMock())

    assert result == {
        "event_id": "evt_1",
        "event_type": "invoice.payment_failed",
        "status": "duplicate",
    }


@pytest.mark.asyncio
async def test_handle_stripe_webhook_dispatches_external_effects_after_commit():
    from api.core.monetization.webhook_handler_service import handle_stripe_webhook

    order = []
    action = MagicMock()

    async def process(*_args, post_commit_actions, **_kwargs):
        post_commit_actions.append(action)
        return "processed"

    db = AsyncMock()
    db.commit = AsyncMock(side_effect=lambda: order.append("commit"))
    dispatch = MagicMock(side_effect=lambda _actions: order.append("dispatch"))
    with (
        patch(
            "api.core.monetization.webhook_handler_service.get_webhook_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.prepare_stripe_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.claim_webhook_event",
            new=AsyncMock(return_value="claimed"),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.process_stripe_event",
            new=AsyncMock(side_effect=process),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.update_webhook_status",
            new=AsyncMock(),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.dispatch_post_commit_actions",
            dispatch,
        ),
    ):
        result = await handle_stripe_webhook(
            "evt_post_commit",
            "customer.subscription.created",
            {},
            db,
        )

    assert result["status"] == "processed"
    assert order == ["commit", "dispatch"]
    dispatch.assert_called_once_with([action])


@pytest.mark.asyncio
async def test_handle_stripe_webhook_never_dispatches_effects_after_rollback():
    from api.core.monetization.webhook_handler_service import (
        WebhookProcessingUnavailable,
        handle_stripe_webhook,
    )

    action = MagicMock()

    async def process(*_args, post_commit_actions, **_kwargs):
        post_commit_actions.append(action)
        return "processed"

    db = AsyncMock()
    db.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    dispatch = MagicMock()
    with (
        patch(
            "api.core.monetization.webhook_handler_service.get_webhook_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.prepare_stripe_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.claim_webhook_event",
            new=AsyncMock(return_value="claimed"),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.process_stripe_event",
            new=AsyncMock(side_effect=process),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.update_webhook_status",
            new=AsyncMock(),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.mark_webhook_retryable_failure",
            new=AsyncMock(),
        ),
        patch(
            "api.core.monetization.webhook_handler_service.dispatch_post_commit_actions",
            dispatch,
        ),
    ):
        with pytest.raises(WebhookProcessingUnavailable):
            await handle_stripe_webhook(
                "evt_post_commit_rollback",
                "customer.subscription.created",
                {},
                db,
            )

    dispatch.assert_not_called()


def _notification_event(event_type):
    if event_type == "invoice.payment_failed":
        return {
            "id": "in_notification",
            "customer": "cus_notification",
            "attempt_count": 1,
        }
    return {
        "id": "sub_notification",
        "customer": "cus_notification",
        "trial_end": 4_102_444_800,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "email_function"),
    [
        ("invoice.payment_failed", "send_payment_failed"),
        ("customer.subscription.trial_will_end", "send_trial_ending"),
    ],
)
async def test_billing_notification_commits_once_and_replay_does_not_duplicate(
    event_type,
    email_function,
):
    from api.core.monetization import webhook_handler_service

    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="notification@example.com",
        full_name="Notification Customer",
        plan="pro",
    )
    sub = SimpleNamespace(plan="pro", stripe_subscription_id="sub_notification")
    scalar = MagicMock()
    scalar.scalar_one_or_none.return_value = sub
    db = AsyncMock()
    db.execute = AsyncMock(return_value=scalar)
    email = AsyncMock()
    dispatched = []
    order = []
    db.commit = AsyncMock(side_effect=lambda: order.append("commit"))

    def capture(actions):
        order.append("dispatch")
        dispatched.extend(actions)

    with (
        patch.object(
            webhook_handler_service,
            "get_webhook_event",
            new=AsyncMock(
                side_effect=[None, SimpleNamespace(status="processed")]
            ),
        ),
        patch.object(
            webhook_handler_service,
            "prepare_stripe_event",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            webhook_handler_service,
            "claim_webhook_event",
            new=AsyncMock(return_value="claimed"),
        ) as claim,
        patch.object(
            webhook_handler_service,
            "update_webhook_status",
            new=AsyncMock(),
        ),
        patch.object(
            webhook_handler_service,
            "dispatch_post_commit_actions",
            side_effect=capture,
        ),
        patch(
            "api.services.billing_service._get_user_by_stripe_customer_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "api.services.billing_service._write_audit",
            new=AsyncMock(),
        ),
        patch(
            "api.services.subscription_state_machine.handle_payment_failed",
            new=AsyncMock(),
        ),
        patch(
            "api.services.subscription_state_machine.handle_trial_will_end",
            new=AsyncMock(),
        ),
        patch(f"api.services.email_service.{email_function}", new=email),
    ):
        first = await webhook_handler_service.handle_stripe_webhook(
            "evt_notification_once",
            event_type,
            _notification_event(event_type),
            db,
        )
        replay = await webhook_handler_service.handle_stripe_webhook(
            "evt_notification_once",
            event_type,
            _notification_event(event_type),
            db,
        )
        assert order == ["commit", "dispatch"]
        assert len(dispatched) == 1
        email.assert_not_awaited()
        await dispatched[0]()

    assert first["status"] == "processed"
    assert replay["status"] == "duplicate"
    assert claim.await_count == 1
    email.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "email_function"),
    [
        ("invoice.payment_failed", "send_payment_failed"),
        ("customer.subscription.trial_will_end", "send_trial_ending"),
    ],
)
async def test_billing_notification_rollback_never_dispatches(
    event_type,
    email_function,
):
    from api.core.monetization import webhook_handler_service

    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="rollback@example.com",
        full_name="Rollback Customer",
        plan="pro",
    )
    sub = SimpleNamespace(plan="pro", stripe_subscription_id="sub_rollback")
    scalar = MagicMock()
    scalar.scalar_one_or_none.return_value = sub
    db = AsyncMock()
    db.execute = AsyncMock(return_value=scalar)
    db.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    email = AsyncMock()
    dispatch = MagicMock()

    with (
        patch.object(
            webhook_handler_service,
            "get_webhook_event",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            webhook_handler_service,
            "prepare_stripe_event",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            webhook_handler_service,
            "claim_webhook_event",
            new=AsyncMock(return_value="claimed"),
        ),
        patch.object(
            webhook_handler_service,
            "update_webhook_status",
            new=AsyncMock(),
        ),
        patch.object(
            webhook_handler_service,
            "mark_webhook_retryable_failure",
            new=AsyncMock(),
        ),
        patch.object(
            webhook_handler_service,
            "dispatch_post_commit_actions",
            dispatch,
        ),
        patch(
            "api.services.billing_service._get_user_by_stripe_customer_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "api.services.billing_service._write_audit",
            new=AsyncMock(),
        ),
        patch(
            "api.services.subscription_state_machine.handle_payment_failed",
            new=AsyncMock(),
        ),
        patch(
            "api.services.subscription_state_machine.handle_trial_will_end",
            new=AsyncMock(),
        ),
        patch(f"api.services.email_service.{email_function}", new=email),
    ):
        with pytest.raises(webhook_handler_service.WebhookProcessingUnavailable):
            await webhook_handler_service.handle_stripe_webhook(
                "evt_notification_rollback",
                event_type,
                _notification_event(event_type),
                db,
            )

    dispatch.assert_not_called()
    email.assert_not_awaited()


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
