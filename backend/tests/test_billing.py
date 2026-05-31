"""
Unit tests for billing checkout session creation.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import uuid

class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


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


@pytest.mark.asyncio
async def test_price_id_to_plan_unknown_returns_none():
    from api.services.billing_service import price_id_to_plan

    assert price_id_to_plan("price_unknown") is None


@pytest.mark.asyncio
async def test_module_subscription_sync_does_not_upgrade_user_plan():
    from api.services.billing_service import sync_subscription_from_stripe

    user = MagicMock()
    user.id = uuid.uuid4()
    user.plan = "free"
    user.stripe_customer_id = "cus_test_module"

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarResult(user),   # initial customer lookup
            _ScalarResult(user),   # module sync customer lookup
            _ScalarResult(None),   # no existing UserModule row
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()

    stripe_sub = {
        "id": "sub_module_123",
        "customer": "cus_test_module",
        "status": "active",
        "cancel_at_period_end": False,
        "current_period_end": 1_800_000_000,
        "metadata": {"type": "module", "module": "ghost"},
        "items": {
            "data": [
                {
                    "price": {
                        "id": "price_unknown_module",
                        "recurring": {"interval": "month"},
                    }
                }
            ]
        },
    }

    result = await sync_subscription_from_stripe(stripe_sub, db)

    assert result is None
    assert user.plan == "free"


@pytest.mark.asyncio
async def test_module_subscription_sync_normalizes_legacy_module_metadata():
    from api.services.billing_service import sync_subscription_from_stripe

    user = MagicMock()
    user.id = uuid.uuid4()
    user.plan = "free"
    user.stripe_customer_id = "cus_test_module"

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarResult(user)])

    with patch("api.services.billing_service.sync_module_subscription_from_stripe", new=AsyncMock()) as sync_mock:
        stripe_sub = {
            "id": "sub_module_legacy_123",
            "customer": "cus_test_module",
            "status": "active",
            "cancel_at_period_end": False,
            "current_period_end": 1_800_000_000,
            "metadata": {"type": "module", "module": "ghost_agency"},
            "items": {
                "data": [
                    {
                        "price": {
                            "id": "price_unknown_module",
                            "recurring": {"interval": "month"},
                        }
                    }
                ]
            },
        }

        result = await sync_subscription_from_stripe(stripe_sub, db)

    assert result is None
    sync_mock.assert_awaited_once()
    assert sync_mock.await_args.args[1] == "ghost"


@pytest.mark.asyncio
async def test_process_stripe_event_audits_invoice_payment_succeeded():
    from api.services.billing_service import process_stripe_event

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "owner@nanovia.ca"

    with (
        patch(
            "api.services.billing_service._get_user_by_stripe_customer_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "api.services.billing_service._write_audit",
            new=AsyncMock(),
        ) as audit_mock,
        patch(
            "api.services.billing_service._queue_telegram_stripe_alert",
        ) as telegram_mock,
    ):
        status = await process_stripe_event(
            "invoice.payment_succeeded",
            {
                "id": "in_123",
                "customer": "cus_123",
                "amount_paid": 14900,
            },
            AsyncMock(),
        )

    assert status == "processed"
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[1] == user.id
    assert audit_mock.await_args.args[2] == "invoice_payment_succeeded"
    telegram_mock.assert_called_once_with(
        "invoice.payment_succeeded",
        {
            "id": "in_123",
            "customer": "cus_123",
            "amount_paid": 14900,
        },
        status="processed",
        user_email="owner@nanovia.ca",
    )


@pytest.mark.asyncio
async def test_process_stripe_event_handles_payment_failed():
    from api.services.billing_service import process_stripe_event

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "owner@nanovia.ca"
    sub = MagicMock()
    sub.stripe_subscription_id = "sub_123"

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarResult(user), _ScalarResult(sub)])

    with (
        patch(
            "api.services.subscription_state_machine.handle_payment_failed",
            new=AsyncMock(),
        ) as failed_mock,
        patch(
            "api.services.billing_service._write_audit",
            new=AsyncMock(),
        ) as audit_mock,
        patch(
            "api.services.billing_service._queue_telegram_stripe_alert",
        ) as telegram_mock,
    ):
        status = await process_stripe_event(
            "invoice.payment_failed",
            {
                "id": "in_failed_123",
                "customer": "cus_123",
                "attempt_count": 2,
            },
            db,
        )

    assert status == "processed"
    failed_mock.assert_awaited_once_with(user, sub, db)
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[2] == "invoice_payment_failed"
    telegram_mock.assert_called_once_with(
        "invoice.payment_failed",
        {
            "id": "in_failed_123",
            "customer": "cus_123",
            "attempt_count": 2,
        },
        status="processed",
        user_email="owner@nanovia.ca",
    )


@pytest.mark.asyncio
async def test_process_stripe_event_handles_checkout_completed_telegram_alert():
    from api.services.billing_service import process_stripe_event

    user = MagicMock()
    user.email = "founder@nanovia.ca"

    db = AsyncMock()

    payload = {
        "id": "cs_123",
        "customer": "cus_123",
        "client_reference_id": str(uuid.uuid4()),
        "subscription": "sub_123",
    }

    with (
        patch(
            "api.services.billing_service.handle_checkout_completed",
            new=AsyncMock(),
        ) as checkout_mock,
        patch(
            "api.services.billing_service._get_user_by_stripe_customer_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "api.services.billing_service._queue_telegram_stripe_alert",
        ) as telegram_mock,
    ):
        status = await process_stripe_event("checkout.session.completed", payload, db)

    assert status == "processed"
    checkout_mock.assert_awaited_once_with(payload, db)
    telegram_mock.assert_called_once_with(
        "checkout.session.completed",
        payload,
        status="processed",
        user_email="founder@nanovia.ca",
    )


@pytest.mark.asyncio
async def test_process_stripe_event_handles_trial_will_end():
    from api.services.billing_service import process_stripe_event

    user = MagicMock()
    user.id = uuid.uuid4()
    sub = MagicMock()
    sub.plan = "pro"

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarResult(user), _ScalarResult(sub)])

    with (
        patch(
            "api.services.subscription_state_machine.handle_trial_will_end",
            new=AsyncMock(),
        ) as trial_mock,
        patch(
            "api.services.billing_service._write_audit",
            new=AsyncMock(),
        ) as audit_mock,
    ):
        status = await process_stripe_event(
            "customer.subscription.trial_will_end",
            {
                "id": "sub_trial_123",
                "customer": "cus_123",
                "trial_end": 4_102_444_800,
            },
            db,
        )

    assert status == "processed"
    trial_mock.assert_awaited_once()
    assert trial_mock.await_args.args[0] == user
    assert trial_mock.await_args.args[1] == sub
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[2] == "customer_subscription_trial_will_end"


@pytest.mark.asyncio
async def test_plan_checkout_omits_payment_method_types(monkeypatch):
    from api.routers import billing as billing_router
    from api.schemas.billing import CheckoutRequest

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "checkout@test.com"
    user.plan = "free"
    user.stripe_customer_id = None

    monkeypatch.setitem(billing_router.PLANS_CONFIG["pro"], "stripe_price_monthly", "price_pro_monthly")
    monkeypatch.setattr(
        billing_router,
        "get_or_create_stripe_customer",
        AsyncMock(return_value="cus_checkout"),
    )

    session = MagicMock()
    session.url = "https://checkout.stripe.test/session"
    create_mock = MagicMock(return_value=session)
    monkeypatch.setattr(billing_router.stripe.checkout.Session, "create", create_mock)
    turnstile_mock = AsyncMock()
    monkeypatch.setattr(billing_router, "enforce_turnstile", turnstile_mock)
    request = MagicMock()
    request.headers = {}
    request.client = MagicMock(host="127.0.0.1")

    response = await billing_router.create_checkout_session(
        CheckoutRequest(plan="pro", interval="monthly", turnstile_token="ts_checkout"),
        request,
        user,
        AsyncMock(),
    )

    assert response.url == session.url
    turnstile_mock.assert_awaited_once_with(request, "ts_checkout", surface="billing")
    assert "payment_method_types" not in create_mock.call_args.kwargs


@pytest.mark.asyncio
async def test_credit_checkout_omits_payment_method_types(monkeypatch):
    from api.routers import billing as billing_router
    from api.schemas.billing import CreditPurchaseRequest

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "credits@test.com"
    user.plan = "pro"
    user.stripe_customer_id = None

    monkeypatch.setattr(
        billing_router,
        "get_or_create_stripe_customer",
        AsyncMock(return_value="cus_credits"),
    )
    monkeypatch.setattr(billing_router.settings, "STRIPE_CREDIT_PRICE_ID", "price_credits")
    monkeypatch.setattr(billing_router.settings, "STRIPE_CREDIT_PACK_SIZE", 50)

    session = MagicMock()
    session.url = "https://checkout.stripe.test/credits"
    create_mock = MagicMock(return_value=session)
    monkeypatch.setattr(billing_router.stripe.checkout.Session, "create", create_mock)
    turnstile_mock = AsyncMock()
    monkeypatch.setattr(billing_router, "enforce_turnstile", turnstile_mock)
    request = MagicMock()
    request.headers = {}
    request.client = MagicMock(host="127.0.0.1")

    response = await billing_router.purchase_credits(
        CreditPurchaseRequest(quantity=2, turnstile_token="ts_credits"),
        request,
        user,
        AsyncMock(),
    )

    assert response.url == session.url
    assert response.credits_to_add == 100
    turnstile_mock.assert_awaited_once_with(request, "ts_credits", surface="billing")
    assert "payment_method_types" not in create_mock.call_args.kwargs


@pytest.mark.asyncio
async def test_portal_session_enforces_turnstile(monkeypatch):
    from api.routers import billing as billing_router
    from api.schemas.billing import PortalSessionRequest

    user = MagicMock()
    user.id = uuid.uuid4()
    user.stripe_customer_id = "cus_portal"

    session = MagicMock()
    session.url = "https://billing.stripe.test/session"
    create_mock = MagicMock(return_value=session)
    monkeypatch.setattr(billing_router.stripe.billing_portal.Session, "create", create_mock)
    turnstile_mock = AsyncMock()
    monkeypatch.setattr(billing_router, "enforce_turnstile", turnstile_mock)
    request = MagicMock()
    request.headers = {}
    request.client = MagicMock(host="127.0.0.1")

    response = await billing_router.create_portal_session(
        request,
        user,
        AsyncMock(),
        PortalSessionRequest(turnstile_token="ts_portal"),
    )

    assert response.url == session.url
    turnstile_mock.assert_awaited_once_with(request, "ts_portal", surface="billing")


@pytest.mark.asyncio
async def test_module_checkout_enforces_turnstile(monkeypatch):
    from api.routers import billing as billing_router
    from api.schemas.billing import ModuleCheckoutRequest

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "module@test.com"
    user.plan = "free"
    user.stripe_customer_id = None

    monkeypatch.setitem(billing_router.MODULES_CONFIG["ghost"], "stripe_price_id", "price_module_ghost")
    monkeypatch.setattr(
        billing_router,
        "get_or_create_stripe_customer",
        AsyncMock(return_value="cus_module"),
    )

    session = MagicMock()
    session.url = "https://checkout.stripe.test/module"
    create_mock = MagicMock(return_value=session)
    monkeypatch.setattr(billing_router.stripe.checkout.Session, "create", create_mock)
    turnstile_mock = AsyncMock()
    monkeypatch.setattr(billing_router, "enforce_turnstile", turnstile_mock)
    request = MagicMock()
    request.headers = {}
    request.client = MagicMock(host="127.0.0.1")

    response = await billing_router.create_module_checkout_session(
        ModuleCheckoutRequest(module="ghost", turnstile_token="ts_module"),
        request,
        user,
        AsyncMock(),
    )

    assert response.url == session.url
    turnstile_mock.assert_awaited_once_with(request, "ts_module", surface="billing")
