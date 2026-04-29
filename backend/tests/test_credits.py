"""
Unit tests for credit_service — add, deduct, idempotency, ledger integrity.
Run with: pytest tests/test_credits.py -v
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.credits = 100
    user.email = "test@example.com"
    user.plan = "pro"
    return user

@pytest.mark.asyncio
async def test_deduct_credits_success(mock_user, mock_db):
    """Deducting credits within balance succeeds."""
    from api.services.credit_service import deduct_credits
    # Two execute calls: (1) re-fetch user with FOR UPDATE lock
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.side_effect = [user_result]
    with (
        patch("api.services.credit_service._realign_credit_projections", new=AsyncMock(return_value=100)),
        patch("api.services.credit_service._sync_workspace_credit_projection", new=AsyncMock()),
    ):
        result = await deduct_credits(mock_user, source="overage", db=mock_db)
    assert result is True
    assert mock_user.credits == 99

@pytest.mark.asyncio
async def test_deduct_credits_insufficient_balance(mock_user, mock_db):
    """Deducting more than balance returns False."""
    from api.services.credit_service import deduct_credits
    mock_user.credits = 0
    # Re-fetch returns the locked user with 0 credits
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.side_effect = [user_result]
    with (
        patch("api.services.credit_service._realign_credit_projections", new=AsyncMock(return_value=0)),
        patch("api.services.credit_service._sync_workspace_credit_projection", new=AsyncMock()),
    ):
        result = await deduct_credits(mock_user, source="overage", db=mock_db)
    assert result is False

@pytest.mark.asyncio
async def test_deduct_credits_idempotency(mock_user, mock_db):
    """Replaying deduction with same idempotency_key returns True without double-deducting."""
    from api.services.credit_service import deduct_credits
    from api.models.credit_ledger import CreditLedger
    existing = MagicMock(spec=CreditLedger)
    # Use a plain MagicMock so scalar_one_or_none() is synchronous
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing
    mock_db.execute.return_value = execute_result
    initial_credits = mock_user.credits
    result = await deduct_credits(mock_user, source="overage", db=mock_db, idempotency_key="idem-123")
    assert result is True
    assert mock_user.credits == initial_credits  # no change
    mock_db.commit.assert_not_called()  # no write

@pytest.mark.asyncio
async def test_add_credits_idempotency(mock_db):
    """Adding credits with same idempotency_key is a no-op on replay."""
    from api.services.credit_service import add_credits
    from api.models.credit_ledger import CreditLedger
    existing = MagicMock(spec=CreditLedger)
    # Use a plain MagicMock for the execute result so scalar_one_or_none() is sync
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing
    mock_db.execute.return_value = execute_result
    result = await add_credits(uuid.uuid4(), 100, source="stripe", db=mock_db, idempotency_key="idem-456")
    assert result == existing
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_realign_credit_projections_uses_ledger_as_authority(mock_user, mock_db):
    """Ledger wins over stale projections and triggers projection sync."""
    from api.services.credit_service import _realign_credit_projections

    mock_user.credits = 7
    with (
        patch("api.services.credit_service._get_authoritative_ledger_balance", new=AsyncMock(return_value=11)),
        patch("api.services.credit_service._sync_workspace_credit_projection", new=AsyncMock()) as sync_mock,
    ):
        authoritative = await _realign_credit_projections(mock_user, mock_db)

    assert authoritative == 11
    assert mock_user.credits == 11
    sync_mock.assert_awaited_once()
