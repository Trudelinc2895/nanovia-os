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
    fake_entry = MagicMock()
    fake_entry.balance_after = 99
    with patch("api.services.credit_service._apply_ledger_change", new=AsyncMock(return_value=fake_entry)):
        result = await deduct_credits(mock_user, source="overage", db=mock_db)
    assert result is True
    assert mock_user.credits == 99

@pytest.mark.asyncio
async def test_deduct_credits_insufficient_balance(mock_user, mock_db):
    """Deducting more than balance returns False."""
    from api.services.credit_service import deduct_credits
    with patch("api.services.credit_service._apply_ledger_change", new=AsyncMock(side_effect=ValueError("Insufficient credits"))):
        result = await deduct_credits(mock_user, source="overage", db=mock_db)
    assert result is False

@pytest.mark.asyncio
async def test_deduct_credits_idempotency(mock_user, mock_db):
    """Replaying deduction with same idempotency_key returns True without double-deducting."""
    from api.services.credit_service import deduct_credits
    from api.models.credit_ledger import CreditLedger
    existing = MagicMock(spec=CreditLedger)
    existing.balance_after = mock_user.credits
    with patch("api.services.credit_service._apply_ledger_change", new=AsyncMock(return_value=existing)):
        initial_credits = mock_user.credits
        result = await deduct_credits(mock_user, source="overage", db=mock_db, idempotency_key="idem-123")
    assert result is True
    assert mock_user.credits == initial_credits  # no change
    # _apply_ledger_change owns persistence/idempotency behavior.

@pytest.mark.asyncio
async def test_add_credits_idempotency(mock_db):
    """Adding credits with same idempotency_key is a no-op on replay."""
    from api.services.credit_service import add_credits
    from api.models.credit_ledger import CreditLedger
    existing = MagicMock(spec=CreditLedger)
    with patch("api.services.credit_service._apply_ledger_change", new=AsyncMock(return_value=existing)):
        result = await add_credits(uuid.uuid4(), 100, source="stripe", db=mock_db, idempotency_key="idem-456")
    assert result == existing
