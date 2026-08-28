"""Synthetic tests for the canonical Nanovia Pro Pilot Stripe contract."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.config import settings
from api.services import pilot_stripe_contract_service as contract


ACCOUNT_ID = "acct_pilot"
PRODUCT_ID = "prod_pilot"
PRICE_ID = "price_pilot"
PAYMENT_LINK_ID = "plink_pilot"
PAYMENT_LINK_URL = "https://buy.stripe.com/test_pilot"
PUBLIC_WEB_URL = "https://nanovia.invalid"
CONFIRMATION_URL = (
    f"{PUBLIC_WEB_URL}/pilot/confirmation?session_id={{CHECKOUT_SESSION_ID}}"
)
PREVIOUS_PRODUCT_ID = "prod_previousPilot"
PREVIOUS_PRICE_ID = "price_previousPilot"
PREVIOUS_PAYMENT_LINK_ID = "plink_previousPilot"
PREVIOUS_PAYMENT_LINK_URL = "https://buy.stripe.com/previousPilot"
REQUEST_ID = "95d9327d-4580-4569-8c0f-5d2a0946a1be"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(settings, "STRIPE_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRODUCT_ID", PRODUCT_ID)
    monkeypatch.setattr(settings, "STRIPE_PILOT_PRICE_ID", PRICE_ID)
    monkeypatch.setattr(settings, "STRIPE_PILOT_PAYMENT_LINK_ID", PAYMENT_LINK_ID)
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PAYMENT_LINK_URL",
        PAYMENT_LINK_URL,
    )
    monkeypatch.setattr(settings, "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON", "[]")
    monkeypatch.setattr(settings, "PUBLIC_WEB_URL", PUBLIC_WEB_URL)


def _config_namespace(**overrides):
    values = {
        "APP_ENV": "test",
        "STRIPE_ACCOUNT_ID": ACCOUNT_ID,
        "STRIPE_PILOT_PRODUCT_ID": PRODUCT_ID,
        "STRIPE_PILOT_PRICE_ID": PRICE_ID,
        "STRIPE_PILOT_PAYMENT_LINK_ID": PAYMENT_LINK_ID,
        "STRIPE_PILOT_PAYMENT_LINK_URL": PAYMENT_LINK_URL,
        "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON": "[]",
        "PUBLIC_WEB_URL": PUBLIC_WEB_URL,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _product() -> dict:
    return {
        "id": PRODUCT_ID,
        "active": True,
        "livemode": False,
        "name": contract.PILOT_PRODUCT_NAME,
        "metadata": {"nanovia_contract": contract.PILOT_CONTRACT_MARKER},
    }


def _price() -> dict:
    return {
        "id": PRICE_ID,
        "active": True,
        "livemode": False,
        "unit_amount": contract.PILOT_AMOUNT_CENTS,
        "currency": contract.PILOT_CURRENCY,
        "type": "one_time",
        "recurring": None,
        "product": _product(),
    }


def _catalog_line_item() -> dict:
    return {
        "quantity": 1,
        "adjustable_quantity": {"enabled": False},
        "price": _price(),
    }


def _checkout_line_item() -> dict:
    return {
        "quantity": 1,
        "amount_subtotal": contract.PILOT_AMOUNT_CENTS,
        "amount_total": contract.PILOT_AMOUNT_CENTS,
        "price": _price(),
    }


def _account() -> dict:
    return {
        "id": ACCOUNT_ID,
        "charges_enabled": True,
        "details_submitted": True,
    }


def _payment_link() -> dict:
    return {
        "id": PAYMENT_LINK_ID,
        "active": True,
        "livemode": False,
        "url": PAYMENT_LINK_URL,
        "allow_promotion_codes": False,
        "automatic_tax": {"enabled": False},
        "customer_creation": "always",
        "after_completion": {
            "type": "redirect",
            "redirect": {"url": CONFIRMATION_URL},
        },
        "metadata": {"nanovia_contract": contract.PILOT_CONTRACT_MARKER},
        "line_items": {"data": [_catalog_line_item()]},
    }


def _session(*, paid: bool = True) -> dict:
    customer_id = "cus_pilot"
    return {
        "id": "cs_pilot",
        "payment_link": PAYMENT_LINK_ID,
        "mode": "payment",
        "livemode": False,
        "currency": "cad",
        "amount_subtotal": 29_700,
        "amount_total": 29_700,
        "total_details": {
            "amount_discount": 0,
            "amount_tax": 0,
            "amount_shipping": 0,
        },
        "discounts": [],
        "metadata": {"nanovia_contract": contract.PILOT_CONTRACT_MARKER},
        "client_reference_id": REQUEST_ID,
        "customer": customer_id,
        "customer_details": {"email": "client@example.com"},
        "payment_status": "paid" if paid else "unpaid",
        "status": "complete" if paid else "open",
        "payment_intent": {
            "id": "pi_pilot",
            "livemode": False,
            "amount": 29_700,
            "amount_received": 29_700 if paid else 0,
            "currency": "cad",
            "customer": customer_id,
            "status": "succeeded" if paid else "processing",
            "latest_charge": {
                "id": "ch_pilot",
                "livemode": False,
                "paid": paid,
                "refunded": False,
                "disputed": False,
                "amount": 29_700,
                "amount_captured": 29_700 if paid else 0,
                "amount_refunded": 0,
                "currency": "cad",
                "customer": customer_id,
                "balance_transaction": {
                    "id": "txn_pilot",
                    "amount": 29_700,
                    "currency": "cad",
                    "fee": 1_174,
                    "net": 28_526,
                },
            },
        },
    }


def _event(session: dict, *, event_type: str = "checkout.session.completed") -> dict:
    return {
        "id": "evt_pilot",
        "type": event_type,
        "api_version": contract.PILOT_STRIPE_API_VERSION,
        "livemode": False,
        "account": ACCOUNT_ID,
        "data": {"object": session},
    }


def _set_path(target: dict, path: str, value) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        if part.isdecimal():
            current = current[int(part)]
        else:
            current = current[part]
    final = parts[-1]
    if final.isdecimal():
        current[int(final)] = value
    else:
        current[final] = value


def _previous_contract_json() -> str:
    return json.dumps(
        [
            {
                "product_id": PREVIOUS_PRODUCT_ID,
                "price_id": PREVIOUS_PRICE_ID,
                "payment_link_id": PREVIOUS_PAYMENT_LINK_ID,
                "payment_link_url": PREVIOUS_PAYMENT_LINK_URL,
            }
        ]
    )


def test_complete_canonical_contract_is_valid_and_margin_is_observable():
    config = contract.load_pilot_stripe_config()
    contract.validate_pilot_provider_contract(_account(), _payment_link(), config)
    verified = contract.validate_pilot_checkout(
        _session(),
        {"data": [_checkout_line_item()]},
        config,
        require_paid=True,
    )

    assert verified.paid is True
    assert verified.gross_amount == 29_700
    assert verified.stripe_fee_amount == 1_174
    assert verified.tax_amount == 0
    assert verified.net_before_delivery_cost == 28_526


@pytest.mark.parametrize(
    ("configured_url", "provider_url"),
    [
        (PAYMENT_LINK_URL, "https://buy.stripe.com:443/test_pilot"),
        ("https://buy.stripe.com:443/test_pilot", PAYMENT_LINK_URL),
    ],
)
def test_payment_link_urls_accept_equivalent_implicit_https_port(
    configured_url,
    provider_url,
):
    config = contract.load_pilot_stripe_config(
        _config_namespace(STRIPE_PILOT_PAYMENT_LINK_URL=configured_url)
    )
    payment_link = _payment_link()
    payment_link["url"] = provider_url

    contract.validate_pilot_provider_contract(_account(), payment_link, config)


@pytest.mark.parametrize(
    "field_name",
    [
        "STRIPE_ACCOUNT_ID",
        "STRIPE_PILOT_PRODUCT_ID",
        "STRIPE_PILOT_PRICE_ID",
        "STRIPE_PILOT_PAYMENT_LINK_ID",
        "STRIPE_PILOT_PAYMENT_LINK_URL",
    ],
)
@pytest.mark.parametrize("missing_value", [None, "", "   "])
def test_each_missing_or_empty_configuration_key_fails_closed(
    field_name,
    missing_value,
):
    with pytest.raises(contract.PilotStripeContractError, match=field_name):
        contract.load_pilot_stripe_config(
            _config_namespace(**{field_name: missing_value})
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("STRIPE_ACCOUNT_ID", "account_wrong"),
        ("STRIPE_PILOT_PRODUCT_ID", "product_wrong"),
        ("STRIPE_PILOT_PRICE_ID", "pilot_price_wrong"),
        ("STRIPE_PILOT_PAYMENT_LINK_ID", "payment_link_wrong"),
        ("STRIPE_PILOT_PAYMENT_LINK_URL", "http://buy.stripe.com/test_pilot"),
        ("STRIPE_PILOT_PAYMENT_LINK_URL", "https://example.invalid/test_pilot"),
        ("STRIPE_PILOT_PAYMENT_LINK_URL", "https://buy.stripe.com/test_pilot?x=1"),
    ],
)
def test_invalid_configuration_formats_fail_closed(field_name, value):
    with pytest.raises(contract.PilotStripeContractError):
        contract.load_pilot_stripe_config(_config_namespace(**{field_name: value}))


def test_production_rejects_obvious_test_payment_link():
    with pytest.raises(contract.PilotStripeContractError, match="mixes test and live"):
        contract.load_pilot_stripe_config(_config_namespace(APP_ENV="production"))


def test_authorized_previous_contracts_are_explicit_complete_and_distinct():
    configs = contract.load_authorized_pilot_stripe_configs(
        _config_namespace(
            STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON=_previous_contract_json()
        )
    )

    assert len(configs) == 2
    assert configs[0].is_current is True
    assert configs[1] == contract.PilotStripeConfig(
        account_id=ACCOUNT_ID,
        product_id=PREVIOUS_PRODUCT_ID,
        price_id=PREVIOUS_PRICE_ID,
            payment_link_id=PREVIOUS_PAYMENT_LINK_ID,
            payment_link_url=PREVIOUS_PAYMENT_LINK_URL,
            confirmation_url=CONFIRMATION_URL,
            livemode=False,
        is_current=False,
    )


@pytest.mark.parametrize(
    "raw_value",
    [
        pytest.param("", id="empty"),
        pytest.param("not-json", id="invalid-json"),
        pytest.param("{}", id="not-list"),
        pytest.param('[{"payment_link_id":"plink_previousPilot"}]', id="partial"),
        pytest.param(
            json.dumps(
                [
                    {
                        "product_id": PREVIOUS_PRODUCT_ID,
                        "price_id": PREVIOUS_PRICE_ID,
                        "payment_link_id": PAYMENT_LINK_ID,
                        "payment_link_url": PREVIOUS_PAYMENT_LINK_URL,
                    }
                ]
            ),
            id="duplicate-link-id",
        ),
        pytest.param(
            json.dumps(
                [
                    {
                        "product_id": PREVIOUS_PRODUCT_ID,
                        "price_id": PREVIOUS_PRICE_ID,
                        "payment_link_id": PREVIOUS_PAYMENT_LINK_ID,
                        "payment_link_url": PAYMENT_LINK_URL,
                    }
                ]
            ),
            id="duplicate-link-url",
        ),
    ],
)
def test_invalid_previous_pilot_contract_registry_fails_closed(raw_value):
    with pytest.raises(contract.PilotStripeContractError):
        contract.load_authorized_pilot_stripe_configs(
            _config_namespace(STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON=raw_value)
        )


@pytest.mark.asyncio
async def test_previous_contract_session_is_fully_verified_after_rotation(monkeypatch):
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON",
        _previous_contract_json(),
    )
    session = _session()
    session["payment_link"] = PREVIOUS_PAYMENT_LINK_ID
    price = _price()
    price["id"] = PREVIOUS_PRICE_ID
    price["active"] = False
    price["product"]["id"] = PREVIOUS_PRODUCT_ID
    price["product"]["active"] = False
    checkout_line = _checkout_line_item()
    checkout_line["price"] = price
    catalog_line = _catalog_line_item()
    catalog_line["price"] = price
    payment_link = _payment_link()
    payment_link.update(
        {
            "id": PREVIOUS_PAYMENT_LINK_ID,
            "url": PREVIOUS_PAYMENT_LINK_URL,
            "active": False,
            "line_items": {"data": [catalog_line]},
        }
    )
    boundaries = {
        "retrieve_pilot_event": AsyncMock(return_value=_event(session)),
        "retrieve_pilot_account": AsyncMock(return_value=_account()),
        "retrieve_pilot_payment_link": AsyncMock(return_value=payment_link),
        "retrieve_pilot_checkout_session": AsyncMock(return_value=session),
        "retrieve_pilot_line_items": AsyncMock(
            return_value={"data": [checkout_line]}
        ),
    }
    for name, boundary in boundaries.items():
        monkeypatch.setattr(contract, name, boundary)

    verified = await contract.verify_pilot_checkout_event(
        "evt_pilot",
        "checkout.session.completed",
        session,
    )

    assert verified.paid is True
    assert verified.config.payment_link_id == PREVIOUS_PAYMENT_LINK_ID
    assert verified.config.price_id == PREVIOUS_PRICE_ID
    assert verified.config.product_id == PREVIOUS_PRODUCT_ID
    boundaries["retrieve_pilot_payment_link"].assert_awaited_once_with(
        PREVIOUS_PAYMENT_LINK_ID
    )


@pytest.mark.asyncio
async def test_foreign_or_temporarily_unverifiable_historical_contract_fails_closed(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON",
        _previous_contract_json(),
    )
    foreign = _session()
    foreign["payment_link"] = "plink_foreign"
    provider_call = AsyncMock(side_effect=contract.PilotStripeProviderUnavailable())
    monkeypatch.setattr(contract, "retrieve_pilot_event", provider_call)

    with pytest.raises(contract.PilotStripeContractError, match="not authorized"):
        await contract.verify_pilot_checkout_event(
            "evt_pilot",
            "checkout.session.completed",
            foreign,
        )
    provider_call.assert_not_awaited()

    authorized = _session()
    authorized["payment_link"] = PREVIOUS_PAYMENT_LINK_ID
    with pytest.raises(contract.PilotStripeProviderUnavailable):
        await contract.verify_pilot_checkout_event(
            "evt_pilot",
            "checkout.session.completed",
            authorized,
        )
    provider_call.assert_awaited_once()


@pytest.mark.parametrize(
    ("target_name", "path", "value"),
    [
        ("account", "id", "acct_wrong"),
        ("account", "charges_enabled", False),
        ("account", "details_submitted", False),
        ("link", "id", "plink_wrong"),
        ("link", "active", False),
        ("link", "livemode", True),
        ("link", "url", "https://buy.stripe.com/test_wrong"),
        ("link", "allow_promotion_codes", True),
        ("link", "automatic_tax.enabled", True),
        ("link", "customer_creation", "if_required"),
        ("link", "after_completion.type", "hosted_confirmation"),
        ("link", "after_completion.redirect.url", "https://example.invalid/complete"),
        ("link", "metadata.nanovia_contract", "other"),
        ("link", "line_items.data.0.quantity", 2),
        ("link", "line_items.data.0.adjustable_quantity.enabled", True),
        ("link", "line_items.data.0.price.id", "price_wrong"),
        ("link", "line_items.data.0.price.active", False),
        ("link", "line_items.data.0.price.unit_amount", 29_699),
        ("link", "line_items.data.0.price.currency", "usd"),
        ("link", "line_items.data.0.price.type", "recurring"),
        ("link", "line_items.data.0.price.recurring", {"interval": "month"}),
        ("link", "line_items.data.0.price.product.id", "prod_wrong"),
        ("link", "line_items.data.0.price.product.active", False),
        ("link", "line_items.data.0.price.product.name", "Other product"),
    ],
)
def test_provider_catalog_mismatches_fail_closed(target_name, path, value):
    account = _account()
    payment_link = _payment_link()
    _set_path(account if target_name == "account" else payment_link, path, value)

    with pytest.raises(contract.PilotStripeContractError):
        contract.validate_pilot_provider_contract(
            account,
            payment_link,
            contract.load_pilot_stripe_config(),
        )


@pytest.mark.parametrize(
    ("target_name", "path", "value"),
    [
        ("session", "payment_link", "plink_wrong"),
        ("session", "mode", "subscription"),
        ("session", "status", "expired"),
        ("session", "livemode", True),
        ("session", "currency", "usd"),
        ("session", "amount_subtotal", 29_699),
        ("session", "amount_total", 29_699),
        ("session", "total_details.amount_discount", 1),
        ("session", "total_details.amount_tax", 1),
        ("session", "metadata.nanovia_contract", "other"),
        ("session", "client_reference_id", "not-a-uuid"),
        ("session", "customer", None),
        ("session", "customer_details.email", ""),
        ("session", "payment_intent.amount", 29_699),
        ("session", "payment_intent.amount_received", 29_699),
        ("session", "payment_intent.currency", "usd"),
        ("session", "payment_intent.customer", "cus_other"),
        ("session", "payment_intent.status", "processing"),
        ("session", "payment_intent.latest_charge.refunded", True),
        ("session", "payment_intent.latest_charge.disputed", True),
        ("session", "payment_intent.latest_charge.amount_refunded", 1),
        ("line", "0.quantity", 2),
        ("line", "0.amount_subtotal", 29_699),
        ("line", "0.amount_total", 29_699),
        ("line", "0.price.id", "price_wrong"),
        ("line", "0.price.unit_amount", 29_699),
        ("line", "0.price.currency", "usd"),
        ("line", "0.price.type", "recurring"),
        ("line", "0.price.product.id", "prod_wrong"),
    ],
)
def test_checkout_and_collected_amount_mismatches_fail_closed(
    target_name,
    path,
    value,
):
    session = _session()
    line_items = [_checkout_line_item()]
    _set_path(session if target_name == "session" else line_items, path, value)

    with pytest.raises(contract.PilotStripeContractError):
        contract.validate_pilot_checkout(
            session,
            {"data": line_items},
            contract.load_pilot_stripe_config(),
            require_paid=True,
        )


def test_unpaid_checkout_is_valid_identity_but_never_paid_fulfillment():
    verified = contract.validate_pilot_checkout(
        _session(paid=False),
        {"data": [_checkout_line_item()]},
        contract.load_pilot_stripe_config(),
        require_paid=False,
    )

    assert verified.paid is False
    assert verified.stripe_fee_amount is None
    with pytest.raises(contract.PilotStripeContractError, match="not paid"):
        contract.validate_pilot_checkout(
            _session(paid=False),
            {"data": [_checkout_line_item()]},
            contract.load_pilot_stripe_config(),
            require_paid=True,
        )


@pytest.mark.asyncio
async def test_authenticated_event_and_provider_objects_form_one_contract(monkeypatch):
    session = _session()
    event = _event(session)
    event["api_version"] = "2023-10-16"
    boundaries = {
        "retrieve_pilot_event": AsyncMock(return_value=event),
        "retrieve_pilot_account": AsyncMock(return_value=_account()),
        "retrieve_pilot_payment_link": AsyncMock(return_value=_payment_link()),
        "retrieve_pilot_checkout_session": AsyncMock(return_value=session),
        "retrieve_pilot_line_items": AsyncMock(
            return_value={"data": [_checkout_line_item()]}
        ),
    }
    for name, boundary in boundaries.items():
        monkeypatch.setattr(contract, name, boundary)

    verified = await contract.verify_pilot_checkout_event(
        "evt_pilot",
        "checkout.session.completed",
        session,
    )

    assert verified.paid is True
    assert verified.payment_intent_id == "pi_pilot"
    assert all(boundary.await_count == 1 for boundary in boundaries.values())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("id", "evt_wrong"),
        ("type", "checkout.session.async_payment_failed"),
        ("livemode", True),
        ("account", "acct_wrong"),
    ],
)
async def test_wrong_event_identity_account_or_mode_fails_closed(
    monkeypatch,
    field_name,
    value,
):
    session = _session()
    event = _event(session)
    event[field_name] = value
    monkeypatch.setattr(contract, "retrieve_pilot_event", AsyncMock(return_value=event))
    monkeypatch.setattr(
        contract,
        "retrieve_pilot_account",
        AsyncMock(return_value=_account()),
    )
    monkeypatch.setattr(
        contract,
        "retrieve_pilot_payment_link",
        AsyncMock(return_value=_payment_link()),
    )

    with pytest.raises(contract.PilotStripeContractError):
        await contract.verify_pilot_checkout_event(
            "evt_pilot",
            "checkout.session.completed",
            session,
        )
