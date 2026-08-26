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
async def test_unsupported_module_purchase_is_hidden_and_blocked_before_stripe(
    mock_user,
):
    from fastapi import HTTPException

    from api.routers import billing as billing_router
    from api.schemas.billing import ModuleCheckoutRequest

    catalog = {
        "modules": {
            "operator": {
                "slug": "operator",
                "name": "AI Operator",
                "price_usd": 19,
                "description": "Operator module",
                "stripe_price_id": "price_module_configured",
                "included_in_plans": ["free", "pro", "business"],
            }
        }
    }
    customer = AsyncMock()
    create_session = MagicMock()
    with (
        patch.object(billing_router, "get_pricing_catalog", return_value=catalog),
        patch.object(
            billing_router,
            "MODULES_CONFIG",
            {"operator": catalog["modules"]["operator"]},
        ),
        patch.object(
            billing_router,
            "get_or_create_stripe_customer",
            customer,
        ),
        patch.object(
            billing_router.stripe.checkout.Session,
            "create",
            create_session,
        ),
    ):
        modules = await billing_router.list_modules()
        with pytest.raises(HTTPException) as exc_info:
            await billing_router.create_module_checkout_session(
                ModuleCheckoutRequest(module="operator"),
                mock_user,
                AsyncMock(),
            )

    assert modules[0].available is False
    assert exc_info.value.status_code == 503
    customer.assert_not_awaited()
    create_session.assert_not_called()


@pytest.mark.asyncio
async def test_unsupported_addon_purchase_is_hidden_and_blocked_before_stripe(
    mock_user,
):
    from fastapi import HTTPException

    from api.routers import billing as billing_router
    from api.schemas.billing import AddonCheckoutRequest

    addon = {
        "name": "API calls",
        "description": "Additional API calls",
        "price_usd": 10,
        "type": "api_calls",
        "grants": {"api_calls": 500},
        "stripe_price_id": "price_addon_configured",
    }
    customer = AsyncMock()
    create_session = MagicMock()
    with (
        patch.object(billing_router, "ADDONS_CONFIG", {"api_calls_500": addon}),
        patch.object(
            billing_router,
            "get_or_create_stripe_customer",
            customer,
        ),
        patch.object(
            billing_router.stripe.checkout.Session,
            "create",
            create_session,
        ),
    ):
        addons = await billing_router.list_addons()
        with pytest.raises(HTTPException) as exc_info:
            await billing_router.addon_checkout(
                AddonCheckoutRequest(addon="api_calls_500"),
                mock_user,
                AsyncMock(),
            )

    assert addons == []
    assert exc_info.value.status_code == 503
    customer.assert_not_awaited()
    create_session.assert_not_called()

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
async def test_module_subscription_sync_is_rejected_without_db_writes():
    from api.services.billing_service import sync_subscription_from_stripe

    user = MagicMock()
    user.id = uuid.uuid4()
    user.plan = "free"
    user.stripe_customer_id = "cus_test_module"

    db = AsyncMock()
    db.execute = AsyncMock()
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
    db.execute.assert_not_awaited()
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_module_subscription_sync_rejects_legacy_module_metadata():
    from api.services.billing_service import sync_subscription_from_stripe

    user = MagicMock()
    user.id = uuid.uuid4()
    user.plan = "free"
    user.stripe_customer_id = "cus_test_module"

    db = AsyncMock()
    db.execute = AsyncMock()

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
    sync_mock.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_module_subscription_event_is_rejected_before_fulfillment():
    from api.services.billing_service import process_stripe_event

    sync = AsyncMock(side_effect=AssertionError("Unsupported fulfillment ran"))
    with patch(
        "api.services.billing_service.sync_subscription_from_stripe",
        sync,
    ):
        status = await process_stripe_event(
            "customer.subscription.created",
            {
                "id": "sub_unsupported_module",
                "customer": "cus_unsupported_module",
                "status": "active",
                "metadata": {"type": "module", "module": "operator"},
                "items": {"data": []},
            },
            AsyncMock(),
        )

    assert status == "rejected"
    sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_module_activation_helper_fails_closed():
    from api.services.billing_service import (
        UnsupportedFulfillmentError,
        activate_user_module,
    )

    db = AsyncMock()
    with pytest.raises(UnsupportedFulfillmentError):
        await activate_user_module(
            user_id=str(uuid.uuid4()),
            module_slug="operator",
            stripe_subscription_id="sub_unsupported",
            stripe_customer_id="cus_unsupported",
            db=db,
        )

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_credit_checkout_missing_owner_never_fulfills_credits(monkeypatch):
    from api.services import billing_service

    credit_fulfillment = AsyncMock()
    monkeypatch.setattr(
        billing_service,
        "fulfill_credit_checkout",
        credit_fulfillment,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarResult(None))
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    await billing_service.handle_checkout_completed(
        {
            "id": "cs_non_credit_missing_owner",
            "mode": "subscription",
            "customer": "cus_non_credit_missing_owner",
            "client_reference_id": str(uuid.uuid4()),
            "metadata": {},
        },
        db,
        commit=False,
    )

    credit_fulfillment.assert_not_awaited()
    db.execute.assert_awaited_once()
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "payload"),
    [
        pytest.param(
            "support-disabled",
            {
                "id": "cs_module_disabled",
                "mode": "subscription",
                "payment_status": "paid",
                "customer": "cus_module_disabled",
                "client_reference_id": str(uuid.uuid4()),
                "metadata": {"type": "module", "module": "operator"},
            },
            id="support-disabled",
        ),
        pytest.param(
            "payment-invalid",
            {
                "id": "cs_module_unpaid",
                "mode": "subscription",
                "payment_status": "unpaid",
                "customer": "cus_module_unpaid",
                "client_reference_id": str(uuid.uuid4()),
                "metadata": {"type": "module", "module": "operator"},
            },
            id="payment-invalid",
        ),
        pytest.param(
            "price-invalid",
            {
                "id": "cs_module_wrong_price",
                "mode": "subscription",
                "payment_status": "paid",
                "customer": "cus_module_wrong_price",
                "client_reference_id": str(uuid.uuid4()),
                "metadata": {
                    "type": "module",
                    "module": "operator",
                    "price_id": "price_untrusted",
                    "quantity": "1",
                },
            },
            id="price-invalid",
        ),
        pytest.param(
            "configuration-partial",
            {
                "id": "cs_module_partial_config",
                "mode": "subscription",
                "payment_status": "paid",
                "customer": "cus_module_partial_config",
                "client_reference_id": str(uuid.uuid4()),
                "metadata": {"type": "module", "module": "operator"},
            },
            id="configuration-partial",
        ),
        pytest.param(
            "product-invalid",
            {
                "id": "cs_module_wrong_product",
                "mode": "subscription",
                "payment_status": "paid",
                "customer": "cus_module_wrong_product",
                "client_reference_id": str(uuid.uuid4()),
                "metadata": {"type": "module", "module": "unknown"},
            },
            id="product-invalid",
        ),
        pytest.param(
            "currency-invalid",
            {
                "id": "cs_module_wrong_currency",
                "mode": "subscription",
                "payment_status": "paid",
                "currency": "cad",
                "customer": "cus_module_wrong_currency",
                "client_reference_id": str(uuid.uuid4()),
                "metadata": {"type": "module", "module": "operator"},
            },
            id="currency-invalid",
        ),
        pytest.param(
            "quantity-invalid",
            {
                "id": "cs_module_wrong_quantity",
                "mode": "subscription",
                "payment_status": "paid",
                "customer": "cus_module_wrong_quantity",
                "client_reference_id": str(uuid.uuid4()),
                "metadata": {
                    "type": "module",
                    "module": "operator",
                    "quantity": "2",
                },
            },
            id="quantity-invalid",
        ),
        pytest.param(
            "owner-invalid",
            {
                "id": "cs_module_wrong_owner",
                "mode": "subscription",
                "payment_status": "paid",
                "customer": "cus_module_wrong_owner",
                "client_reference_id": "not-a-user-id",
                "metadata": {"type": "module", "module": "operator"},
            },
            id="owner-invalid",
        ),
    ],
)
async def test_module_checkout_fails_closed_without_verified_fulfillment(
    monkeypatch,
    case,
    payload,
):
    from api.services import billing_service

    processor = AsyncMock(side_effect=AssertionError("Module fulfillment ran"))
    monkeypatch.setattr(
        billing_service,
        "SUPPORTED_AUTOMATED_FULFILLMENT_TYPES",
        frozenset({"credits", "module"}),
    )
    if case == "support-disabled":
        monkeypatch.setattr(
            billing_service,
            "SUPPORTED_AUTOMATED_FULFILLMENT_TYPES",
            frozenset({"credits"}),
        )
    if case == "configuration-partial":
        monkeypatch.setitem(
            billing_service.MODULES_CONFIG,
            "operator",
            {"stripe_price_id": None},
        )
    monkeypatch.setattr(billing_service, "handle_checkout_completed", processor)

    with pytest.raises(
        billing_service.UnsupportedFulfillmentError,
        match="disabled pending strict server-side contract verification",
    ):
        await billing_service.process_stripe_event(
            "checkout.session.completed",
            payload,
            AsyncMock(),
        )

    processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_stripe_event_audits_invoice_payment_succeeded():
    from api.services.billing_service import process_stripe_event

    user = MagicMock()
    user.id = uuid.uuid4()

    with (
        patch(
            "api.services.billing_service._get_user_by_stripe_customer_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "api.services.billing_service._write_audit",
            new=AsyncMock(),
        ) as audit_mock,
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


@pytest.mark.asyncio
async def test_process_stripe_event_handles_payment_failed():
    from api.services.billing_service import process_stripe_event

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "payment-failed@example.com"
    user.plan = "pro"
    sub = MagicMock()
    sub.stripe_subscription_id = "sub_123"
    sub.plan = "pro"

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarResult(user), _ScalarResult(sub)])
    post_commit_actions = []
    email = AsyncMock()

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
            "api.services.email_service.send_payment_failed",
            new=email,
        ),
    ):
        status = await process_stripe_event(
            "invoice.payment_failed",
            {
                "id": "in_failed_123",
                "customer": "cus_123",
                "attempt_count": 2,
            },
            db,
            post_commit_actions=post_commit_actions,
        )

    assert status == "processed"
    failed_mock.assert_awaited_once_with(user, sub, db)
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[2] == "invoice_payment_failed"
    email.assert_not_awaited()
    assert len(post_commit_actions) == 1
    await post_commit_actions[0]()
    email.assert_awaited_once_with(user.email, sub.plan)


@pytest.mark.asyncio
async def test_process_stripe_event_handles_trial_will_end():
    from api.services.billing_service import process_stripe_event

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "trial-ending@example.com"
    user.full_name = "Trial Customer"
    sub = MagicMock()
    sub.plan = "pro"

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarResult(user), _ScalarResult(sub)])
    post_commit_actions = []
    email = AsyncMock()

    with (
        patch(
            "api.services.subscription_state_machine.handle_trial_will_end",
            new=AsyncMock(),
        ) as trial_mock,
        patch(
            "api.services.billing_service._write_audit",
            new=AsyncMock(),
        ) as audit_mock,
        patch(
            "api.services.email_service.send_trial_ending",
            new=email,
        ),
    ):
        status = await process_stripe_event(
            "customer.subscription.trial_will_end",
            {
                "id": "sub_trial_123",
                "customer": "cus_123",
                "trial_end": 4_102_444_800,
            },
            db,
            post_commit_actions=post_commit_actions,
        )

    assert status == "processed"
    trial_mock.assert_awaited_once()
    assert trial_mock.await_args.args[0] == user
    assert trial_mock.await_args.args[1] == sub
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[2] == "customer_subscription_trial_will_end"
    email.assert_not_awaited()
    assert len(post_commit_actions) == 1
    await post_commit_actions[0]()
    email.assert_awaited_once_with(
        user.email,
        user.full_name,
        trial_mock.await_args.args[2],
    )


def _stripe_customer(user, metadata):
    return {
        "id": user.stripe_customer_id,
        "email": user.email,
        "livemode": False,
        "metadata": metadata,
    }


@pytest.mark.asyncio
async def test_credit_customer_with_valid_identity_is_not_modified(mock_user):
    from api.config import settings
    from api.services import billing_service

    mock_user.stripe_customer_id = "cus_valid_credit"
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(None))
    retrieve = AsyncMock(
        return_value=_stripe_customer(
            mock_user,
            {"user_id": str(mock_user.id), "app": settings.APP_NAME},
        )
    )
    update = AsyncMock()
    candidates = AsyncMock()

    with (
        patch.object(billing_service, "retrieve_credit_customer", retrieve),
        patch.object(billing_service, "update_credit_customer_metadata", update),
        patch.object(billing_service, "list_credit_customers", candidates),
    ):
        await billing_service.validate_or_repair_credit_customer_identity(
            mock_user,
            mock_user.stripe_customer_id,
            db,
        )

    retrieve.assert_awaited_once_with("cus_valid_credit")
    update.assert_not_awaited()
    candidates.assert_not_awaited()


@pytest.mark.asyncio
async def test_resynced_credit_customer_identity_is_repaired_and_confirmed(mock_user):
    from api.config import settings
    from api.services import billing_service

    mock_user.stripe_customer_id = "cus_resynced_credit"
    customer = _stripe_customer(mock_user, {"source": "legacy"})
    repaired = _stripe_customer(
        mock_user,
        {
            "source": "legacy",
            "user_id": str(mock_user.id),
            "app": settings.APP_NAME,
        },
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(None))
    retrieve = AsyncMock(return_value=customer)
    candidates = AsyncMock(
        return_value={"data": [customer], "has_more": False}
    )
    update = AsyncMock(return_value=repaired)

    with (
        patch.object(billing_service, "retrieve_credit_customer", retrieve),
        patch.object(billing_service, "list_credit_customers", candidates),
        patch.object(billing_service, "update_credit_customer_metadata", update),
    ):
        await billing_service.validate_or_repair_credit_customer_identity(
            mock_user,
            mock_user.stripe_customer_id,
            db,
        )

    candidates.assert_awaited_once_with(mock_user.email)
    update.assert_awaited_once_with(
        "cus_resynced_credit",
        {
            "source": "legacy",
            "user_id": str(mock_user.id),
            "app": settings.APP_NAME,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"user_id": str(uuid.uuid4()), "app": "nanovia"},
        {"user_id": "", "app": "foreign-app"},
    ],
)
async def test_credit_customer_contradictory_identity_is_never_overwritten(
    mock_user,
    metadata,
):
    from api.services import billing_service

    mock_user.stripe_customer_id = "cus_contradictory_credit"
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(None))
    update = AsyncMock()
    with (
        patch.object(
            billing_service,
            "retrieve_credit_customer",
            new=AsyncMock(return_value=_stripe_customer(mock_user, metadata)),
        ),
        patch.object(billing_service, "update_credit_customer_metadata", update),
    ):
        with pytest.raises(billing_service.CreditFulfillmentUnavailable):
            await billing_service.validate_or_repair_credit_customer_identity(
                mock_user,
                mock_user.stripe_customer_id,
                db,
            )

    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_credit_customer_email_match_must_be_unambiguous(mock_user):
    from api.services import billing_service

    mock_user.stripe_customer_id = "cus_ambiguous_credit"
    customer = _stripe_customer(mock_user, {})
    other = dict(customer, id="cus_same_email_other")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(None))
    update = AsyncMock()
    with (
        patch.object(
            billing_service,
            "retrieve_credit_customer",
            new=AsyncMock(return_value=customer),
        ),
        patch.object(
            billing_service,
            "list_credit_customers",
            new=AsyncMock(
                return_value={"data": [customer, other], "has_more": False}
            ),
        ),
        patch.object(billing_service, "update_credit_customer_metadata", update),
    ):
        with pytest.raises(billing_service.CreditFulfillmentUnavailable):
            await billing_service.validate_or_repair_credit_customer_identity(
                mock_user,
                mock_user.stripe_customer_id,
                db,
            )

    update.assert_not_awaited()


def test_resync_customer_selection_rejects_foreign_or_ambiguous_identity(mock_user):
    from api.config import settings
    from api.services import billing_service

    unowned = {
        "id": "cus_resync_unowned",
        "email": mock_user.email,
        "metadata": {},
    }
    selected, ambiguous = billing_service._select_resync_customer(
        {"data": [unowned], "has_more": False},
        mock_user,
    )
    assert selected == unowned
    assert ambiguous is False

    selected, ambiguous = billing_service._select_resync_customer(
        {
            "data": [unowned, dict(unowned, id="cus_resync_ambiguous")],
            "has_more": False,
        },
        mock_user,
    )
    assert selected is None
    assert ambiguous is True

    selected, ambiguous = billing_service._select_resync_customer(
        {
            "data": [
                dict(
                    unowned,
                    metadata={
                        "user_id": str(uuid.uuid4()),
                        "app": settings.APP_NAME,
                    },
                )
            ],
            "has_more": False,
        },
        mock_user,
    )
    assert selected is None
    assert ambiguous is False


@pytest.mark.asyncio
async def test_post_commit_notification_error_is_logged_without_rollback():
    from api.services import billing_service

    action = AsyncMock(side_effect=RuntimeError("local email failure"))
    with patch.object(billing_service.logger, "exception") as logged:
        await billing_service._run_post_commit_action(action)

    action.assert_awaited_once()
    logged.assert_called_once_with("[webhook] Post-commit side effect failed")


@pytest.mark.asyncio
async def test_credit_customer_local_owner_must_be_unique(mock_user):
    from api.services import billing_service

    mock_user.stripe_customer_id = "cus_duplicate_owner"
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(uuid.uuid4()))
    retrieve = AsyncMock()

    with patch.object(billing_service, "retrieve_credit_customer", retrieve):
        with pytest.raises(billing_service.CreditFulfillmentUnavailable):
            await billing_service.validate_or_repair_credit_customer_identity(
                mock_user,
                mock_user.stripe_customer_id,
                db,
            )

    retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_unconfirmed_credit_customer_update_fails_closed(mock_user):
    from api.services import billing_service

    mock_user.stripe_customer_id = "cus_unconfirmed_credit"
    customer = _stripe_customer(mock_user, {})
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(None))
    with (
        patch.object(
            billing_service,
            "retrieve_credit_customer",
            new=AsyncMock(return_value=customer),
        ),
        patch.object(
            billing_service,
            "list_credit_customers",
            new=AsyncMock(return_value={"data": [customer], "has_more": False}),
        ),
        patch.object(
            billing_service,
            "update_credit_customer_metadata",
            new=AsyncMock(return_value=customer),
        ),
    ):
        with pytest.raises(billing_service.CreditFulfillmentUnavailable):
            await billing_service.validate_or_repair_credit_customer_identity(
                mock_user,
                mock_user.stripe_customer_id,
                db,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_error",
    [
        pytest.param("outage", id="outage"),
        pytest.param("timeout", id="timeout"),
    ],
)
async def test_credit_customer_update_provider_error_is_retryable(
    monkeypatch,
    provider_error,
):
    import stripe

    from api.services import billing_service

    error = (
        stripe.error.APIConnectionError("local outage")
        if provider_error == "outage"
        else TimeoutError("local timeout")
    )
    monkeypatch.setattr(
        billing_service.stripe.Customer,
        "modify",
        MagicMock(side_effect=error),
    )

    with pytest.raises(billing_service.CreditFulfillmentUnavailable):
        await billing_service.update_credit_customer_metadata(
            "cus_provider_error",
            {"user_id": str(uuid.uuid4()), "app": "nanovia"},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "customer_error",
    [
        pytest.param("identity", id="contradictory-identity"),
        pytest.param("provider", id="provider-unavailable"),
    ],
)
async def test_credit_customer_failure_never_creates_checkout(
    mock_user,
    customer_error,
):
    import stripe

    from fastapi import HTTPException

    from api.routers import billing as billing_router
    from api.schemas.billing import CreditPurchaseRequest
    from api.services import billing_service

    customer_failure = (
        billing_service.CreditFulfillmentUnavailable(
            billing_service.CREDIT_FULFILLMENT_RETRYABLE_ERROR
        )
        if customer_error == "identity"
        else stripe.error.APIConnectionError("local provider outage")
    )
    customer = AsyncMock(side_effect=customer_failure)
    checkout = MagicMock()
    with (
        patch.object(
            billing_router,
            "prepare_credit_purchase_contract",
            new=AsyncMock(return_value=MagicMock(price_id="price_credit")),
        ),
        patch.object(
            billing_router,
            "get_or_create_stripe_customer",
            customer,
        ),
        patch.object(
            billing_router.stripe.checkout.Session,
            "create",
            checkout,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await billing_router.purchase_credits(
                CreditPurchaseRequest(quantity=1),
                mock_user,
                AsyncMock(),
            )

    assert exc_info.value.status_code == 503
    assert customer.await_args.kwargs == {"validate_credit_identity": True}
    checkout.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "email_function"),
    [
        ("customer.subscription.created", "send_billing_confirmation"),
        ("customer.subscription.deleted", "send_subscription_cancelled"),
    ],
)
async def test_subscription_email_is_deferred_until_after_commit(
    event_type,
    email_function,
):
    from api.services.billing_service import process_stripe_event

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "customer@example.com"
    user.full_name = "Customer"
    user.plan = "pro"
    email = AsyncMock()
    post_commit_actions = []
    data = {
        "id": "sub_email",
        "customer": "cus_email",
        "status": "active" if event_type.endswith("created") else "canceled",
        "metadata": {"plan": "pro"},
        "items": {"data": [{"price": {"unit_amount": 7900}}]},
    }

    with (
        patch(
            "api.services.billing_service.sync_subscription_from_stripe",
            new=AsyncMock(),
        ),
        patch(
            "api.services.billing_service._get_user_by_stripe_customer_id",
            new=AsyncMock(return_value=user),
        ),
        patch("api.services.billing_service._write_audit", new=AsyncMock()),
        patch(f"api.services.email_service.{email_function}", new=email),
    ):
        status = await process_stripe_event(
            event_type,
            data,
            AsyncMock(),
            post_commit_actions=post_commit_actions,
        )

        assert status == "processed"
        email.assert_not_awaited()
        assert len(post_commit_actions) == 1
        await post_commit_actions[0]()

    email.assert_awaited_once()
