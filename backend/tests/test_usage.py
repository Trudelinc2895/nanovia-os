"""Unit tests for usage metering."""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.plan = "free"
    user.credits = 0
    return user

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db

@pytest.mark.asyncio
async def test_unlimited_plan_always_allowed():
    """Business plan (limit=-1) always returns allowed."""
    from api.services.usage_service import check_and_charge_usage
    user = MagicMock()
    user.id = uuid.uuid4()
    user.plan = "business"
    user.credits = 0
    db = AsyncMock()
    with patch("api.services.usage_service._get_redis") as mock_redis:
        redis_mock = AsyncMock()
        redis_mock.get.return_value = "9999999"
        mock_redis.return_value = redis_mock
        allowed, reason = await check_and_charge_usage(user, db)
    assert allowed is True
    assert reason == "unlimited"

@pytest.mark.asyncio
async def test_within_limit(mock_user, mock_db):
    """User under quota returns within_limit."""
    from api.services.usage_service import check_and_charge_usage
    mock_user.plan = "pro"
    with patch("api.services.usage_service._get_redis") as mock_redis:
        redis_mock = AsyncMock()
        redis_mock.get.return_value = "10"  # well under 1000
        mock_redis.return_value = redis_mock
        allowed, reason = await check_and_charge_usage(mock_user, mock_db)
    assert allowed is True
    assert reason == "within_limit"

@pytest.mark.asyncio
async def test_limit_exceeded_no_credits(mock_user, mock_db):
    """User over quota with no credits returns limit_exceeded."""
    from api.services.usage_service import check_and_charge_usage
    mock_user.plan = "free"
    mock_user.credits = 0
    with (
        patch("api.services.usage_service._get_redis") as mock_redis,
        patch(
            "api.services.credit_service.get_authoritative_credit_balance",
            new=AsyncMock(return_value=0),
        ),
    ):
        redis_mock = AsyncMock()
        redis_mock.get.return_value = "9999"  # way over free limit (50)
        mock_redis.return_value = redis_mock
        allowed, reason = await check_and_charge_usage(mock_user, mock_db)
    assert allowed is False
    assert reason == "limit_exceeded"

@pytest.mark.asyncio
async def test_redis_unavailable_fail_open(mock_user, mock_db):
    """Redis down returns fail-open (allowed=True)."""
    from api.services.usage_service import check_and_charge_usage
    mock_user.plan = "pro"
    with patch("api.services.usage_service.settings.APP_ENV", "development"), patch(
        "api.services.usage_service._get_redis",
        side_effect=Exception("Redis down"),
    ):
        allowed, reason = await check_and_charge_usage(mock_user, mock_db)
    assert allowed is True
    assert reason == "redis_unavailable"


@pytest.mark.asyncio
async def test_redis_unavailable_fail_closed_in_production(mock_user, mock_db):
    """Production blocks metered usage when Redis is unavailable."""
    from api.services.usage_service import check_and_charge_usage

    mock_user.plan = "pro"
    with patch("api.services.usage_service.settings.APP_ENV", "production"), patch(
        "api.services.usage_service._get_redis",
        side_effect=Exception("Redis down"),
    ):
        allowed, reason = await check_and_charge_usage(mock_user, mock_db)

    assert allowed is False
    assert reason == "metering_unavailable"


@pytest.mark.asyncio
async def test_overage_deducts_credit_when_allowed(mock_user, mock_db):
    """Over-quota paid plans consume credits when overage is enabled."""
    from api.services.usage_service import check_and_charge_usage

    mock_user.plan = "pro"
    mock_user.credits = 3
    with (
        patch("api.services.usage_service._get_redis") as mock_redis,
        patch(
            "api.services.credit_service.get_authoritative_credit_balance",
            new=AsyncMock(return_value=3),
        ),
        patch("api.services.credit_service.deduct_credits", new=AsyncMock(return_value=True)) as deduct_mock,
    ):
        redis_mock = AsyncMock()
        redis_mock.get.return_value = "1000"
        redis_mock.setex = AsyncMock(return_value=True)
        mock_redis.return_value = redis_mock
        allowed, reason = await check_and_charge_usage(mock_user, mock_db)

    assert allowed is True
    assert reason == "credit_deducted"
    deduct_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_overage_uses_ledger_balance_not_stale_projection(mock_user, mock_db):
    """Overage decisions must read the authoritative ledger balance, not user.credits."""
    from api.services.usage_service import check_and_charge_usage

    mock_user.plan = "pro"
    mock_user.credits = 0
    with (
        patch("api.services.usage_service._get_redis") as mock_redis,
        patch(
            "api.services.credit_service.get_authoritative_credit_balance",
            new=AsyncMock(return_value=2),
        ),
        patch("api.services.credit_service.deduct_credits", new=AsyncMock(return_value=True)) as deduct_mock,
    ):
        redis_mock = AsyncMock()
        redis_mock.get.return_value = "1000"
        redis_mock.setex = AsyncMock(return_value=True)
        mock_redis.return_value = redis_mock
        allowed, reason = await check_and_charge_usage(mock_user, mock_db)

    assert allowed is True
    assert reason == "credit_deducted"
    deduct_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_usage_writes_usage_event(mock_user, mock_db):
    """Usage recording also emits a workspace-compatible usage event."""
    from api.services.usage_service import record_usage
    from api.models.usage_record import UsageRecord
    from api.models.workspace_billing import UsageEvent

    workspace_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    record = await record_usage(
        user_id=mock_user.id,
        module="operator",
        tokens_used=42,
        db=mock_db,
        unit_cost_credits=1,
        workspace_id=workspace_id,
        actor_user_id=actor_id,
        request_id="req-123",
        idempotency_key="idem-usage-123",
    )

    added_instances = [call.args[0] for call in mock_db.add.call_args_list]
    assert isinstance(record, UsageRecord)
    assert any(isinstance(instance, UsageRecord) for instance in added_instances)

    event = next(instance for instance in added_instances if isinstance(instance, UsageEvent))
    assert event.workspace_id == workspace_id
    assert event.actor_user_id == actor_id
    assert event.request_id == "req-123"
    assert event.idempotency_key == "idem-usage-123"
    assert event.event_type == "operator"
    assert event.quantity == 1
    assert event.event_metadata["tokens_used"] == 42
    assert event.event_metadata["unit_cost_credits"] == 1


@pytest.mark.asyncio
async def test_record_usage_uses_request_context_for_idempotency(mock_user, mock_db):
    """Usage events inherit the request id to keep idempotency stable across a retried request."""
    from api.core.logging import set_request_id
    from api.services.usage_service import record_usage
    from api.models.workspace_billing import UsageEvent

    set_request_id("req-ctx-123")

    await record_usage(
        user_id=mock_user.id,
        module="operator",
        tokens_used=5,
        db=mock_db,
        workspace_id=mock_user.id,
        actor_user_id=mock_user.id,
    )

    event = next(call.args[0] for call in mock_db.add.call_args_list if isinstance(call.args[0], UsageEvent))
    assert event.request_id == "req-ctx-123"
    assert event.idempotency_key == f"usage:{mock_user.id}:operator:req-ctx-123"
