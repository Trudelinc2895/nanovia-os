"""Canonical, fail-closed Stripe contract for Nanovia Pro Pilot.

Provider access is isolated behind bounded async functions so tests can replace
every Stripe boundary with synthetic objects. No secret or customer data is
included in validation errors.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

import stripe

from api.config import settings


PILOT_PRODUCT_NAME = "Nanovia Pro Pilot"
PILOT_CONTRACT_MARKER = "nanovia_pro_pilot_v1"
PILOT_AMOUNT_CENTS = 29_700
PILOT_CURRENCY = "cad"
PILOT_STRIPE_API_VERSION = "2024-12-18.acacia"
PILOT_WEBHOOK_TOLERANCE_SECONDS = 300
PILOT_PROVIDER_TIMEOUT_SECONDS = 8.0
PILOT_PROVIDER_MAX_ATTEMPTS = 2

PILOT_CHECKOUT_EVENT_TYPES = frozenset(
    {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
    }
)
PILOT_REVERSAL_EVENT_TYPES = frozenset(
    {
        "charge.refunded",
        "charge.dispute.created",
        "charge.dispute.closed",
        "payment_intent.canceled",
        "refund.created",
        "refund.updated",
    }
)

_ID_PATTERNS = {
    "STRIPE_ACCOUNT_ID": re.compile(r"^acct_[A-Za-z0-9]+$"),
    "STRIPE_PILOT_PRODUCT_ID": re.compile(r"^prod_[A-Za-z0-9]+$"),
    "STRIPE_PILOT_PRICE_ID": re.compile(r"^price_[A-Za-z0-9]+$"),
    "STRIPE_PILOT_PAYMENT_LINK_ID": re.compile(r"^plink_[A-Za-z0-9]+$"),
}


class PilotStripeContractError(RuntimeError):
    """Permanent contract mismatch that must never grant Pilot value."""


class PilotStripeProviderUnavailable(RuntimeError):
    """Bounded provider verification could not complete safely."""


@dataclass(frozen=True)
class PilotStripeConfig:
    account_id: str
    product_id: str
    price_id: str
    payment_link_id: str
    payment_link_url: str
    livemode: bool
    is_current: bool = True


@dataclass(frozen=True)
class VerifiedPilotCheckout:
    session: Any
    line_item: Any
    config: PilotStripeConfig
    request_id: uuid.UUID
    customer_id: str
    customer_email: str
    payment_intent_id: str
    paid: bool
    gross_amount: int
    stripe_fee_amount: int | None
    tax_amount: int

    @property
    def net_before_delivery_cost(self) -> int | None:
        if self.stripe_fee_amount is None:
            return None
        return self.gross_amount - self.stripe_fee_amount - self.tax_amount


def stripe_field(value: Any, field: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(field, default)
    return getattr(value, field, default)


def stripe_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    candidate = stripe_field(value, "id")
    return str(candidate) if candidate else None


def stripe_list_data(value: Any) -> list[Any]:
    return list(stripe_field(value, "data", []) or [])


def _contract_error(message: str) -> PilotStripeContractError:
    return PilotStripeContractError(message)


def _required_text(settings_obj: Any, field_name: str) -> str:
    value = getattr(settings_obj, field_name, None)
    if not isinstance(value, str) or not value.strip():
        raise _contract_error(f"{field_name} is required")
    return value.strip()


def _canonical_payment_link_url(
    value: Any,
    *,
    error_message: str,
) -> tuple[str, str, int, str]:
    if not isinstance(value, str):
        raise _contract_error(error_message)
    try:
        parsed_url = urlsplit(value)
        port = parsed_url.port
    except ValueError as exc:
        raise _contract_error(error_message) from exc
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "buy.stripe.com"
        or port not in (None, 443)
        or parsed_url.username is not None
        or parsed_url.password is not None
        or not parsed_url.path.strip("/")
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise _contract_error(error_message)
    return parsed_url.scheme, parsed_url.hostname, 443, parsed_url.path


def load_pilot_stripe_config(settings_obj: Any = settings) -> PilotStripeConfig:
    """Load all five canonical identifiers atomically or fail closed."""
    values = {
        field_name: _required_text(settings_obj, field_name)
        for field_name in (
            "STRIPE_ACCOUNT_ID",
            "STRIPE_PILOT_PRODUCT_ID",
            "STRIPE_PILOT_PRICE_ID",
            "STRIPE_PILOT_PAYMENT_LINK_ID",
            "STRIPE_PILOT_PAYMENT_LINK_URL",
        )
    }
    for field_name, pattern in _ID_PATTERNS.items():
        if pattern.fullmatch(values[field_name]) is None:
            raise _contract_error(f"{field_name} has an invalid format")

    canonical_payment_link_url = _canonical_payment_link_url(
        values["STRIPE_PILOT_PAYMENT_LINK_URL"],
        error_message="STRIPE_PILOT_PAYMENT_LINK_URL is invalid",
    )

    livemode = getattr(settings_obj, "APP_ENV", "") == "production"
    if livemode and canonical_payment_link_url[3].lstrip("/").startswith("test_"):
        raise _contract_error("Pilot Payment Link mixes test and live modes")

    return PilotStripeConfig(
        account_id=values["STRIPE_ACCOUNT_ID"],
        product_id=values["STRIPE_PILOT_PRODUCT_ID"],
        price_id=values["STRIPE_PILOT_PRICE_ID"],
        payment_link_id=values["STRIPE_PILOT_PAYMENT_LINK_ID"],
        payment_link_url=values["STRIPE_PILOT_PAYMENT_LINK_URL"],
        livemode=livemode,
    )


_PREVIOUS_CONTRACT_KEYS = frozenset(
    {"product_id", "price_id", "payment_link_id", "payment_link_url"}
)


def load_authorized_pilot_stripe_configs(
    settings_obj: Any = settings,
) -> tuple[PilotStripeConfig, ...]:
    """Load the current contract and every explicitly authorized retired contract."""
    current = load_pilot_stripe_config(settings_obj)
    raw_previous = getattr(
        settings_obj,
        "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON",
        "[]",
    )
    if not isinstance(raw_previous, str) or not raw_previous.strip():
        raise _contract_error("STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON must be a JSON list")
    try:
        previous_values = json.loads(raw_previous)
    except (TypeError, ValueError) as exc:
        raise _contract_error(
            "STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON must be valid JSON"
        ) from exc
    if not isinstance(previous_values, list):
        raise _contract_error("STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON must be a JSON list")

    configs = [current]
    payment_link_ids = {current.payment_link_id}
    canonical_urls = {
        _canonical_payment_link_url(
            current.payment_link_url,
            error_message="STRIPE_PILOT_PAYMENT_LINK_URL is invalid",
        )
    }
    for index, value in enumerate(previous_values):
        label = f"STRIPE_PILOT_PREVIOUS_CONTRACTS_JSON[{index}]"
        if not isinstance(value, dict) or set(value) != _PREVIOUS_CONTRACT_KEYS:
            raise _contract_error(f"{label} must contain exactly the Pilot contract keys")
        product_id = value.get("product_id")
        price_id = value.get("price_id")
        payment_link_id = value.get("payment_link_id")
        payment_link_url = value.get("payment_link_url")
        for field_name, field_value, pattern_name in (
            ("product_id", product_id, "STRIPE_PILOT_PRODUCT_ID"),
            ("price_id", price_id, "STRIPE_PILOT_PRICE_ID"),
            ("payment_link_id", payment_link_id, "STRIPE_PILOT_PAYMENT_LINK_ID"),
        ):
            if (
                not isinstance(field_value, str)
                or not field_value
                or _ID_PATTERNS[pattern_name].fullmatch(field_value) is None
            ):
                raise _contract_error(f"{label}.{field_name} has an invalid format")
        canonical_url = _canonical_payment_link_url(
            payment_link_url,
            error_message=f"{label}.payment_link_url is invalid",
        )
        if current.livemode and canonical_url[3].lstrip("/").startswith("test_"):
            raise _contract_error(f"{label} mixes test and live modes")
        if payment_link_id in payment_link_ids:
            raise _contract_error(f"{label}.payment_link_id is duplicated")
        if canonical_url in canonical_urls:
            raise _contract_error(f"{label}.payment_link_url is duplicated")
        payment_link_ids.add(payment_link_id)
        canonical_urls.add(canonical_url)
        configs.append(
            PilotStripeConfig(
                account_id=current.account_id,
                product_id=product_id,
                price_id=price_id,
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                livemode=current.livemode,
                is_current=False,
            )
        )
    return tuple(configs)


def find_authorized_pilot_stripe_config(
    payment_link: Any,
    settings_obj: Any = settings,
) -> PilotStripeConfig | None:
    payment_link_id = stripe_id(payment_link)
    return next(
        (
            config
            for config in load_authorized_pilot_stripe_configs(settings_obj)
            if config.payment_link_id == payment_link_id
        ),
        None,
    )


def is_canonical_payment_link(value: Any, config: PilotStripeConfig) -> bool:
    return stripe_id(value) == config.payment_link_id


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _contract_error(message)


def _require_exact_int(value: Any, expected: int, message: str) -> None:
    _require(not isinstance(value, bool) and isinstance(value, int), message)
    _require(value == expected, message)


def _metadata(value: Any) -> dict[str, Any]:
    candidate = stripe_field(value, "metadata", {}) or {}
    return dict(candidate) if isinstance(candidate, dict) else dict(candidate)


def _validate_contract_metadata(value: Any, resource_name: str) -> None:
    metadata = _metadata(value)
    _require(
        metadata.get("nanovia_contract") == PILOT_CONTRACT_MARKER,
        f"{resource_name} contract metadata is missing or contradictory",
    )


def _validate_product(product: Any, config: PilotStripeConfig) -> None:
    _require(not isinstance(product, str), "Pilot Product was not expanded")
    _require(stripe_id(product) == config.product_id, "Pilot Product id mismatch")
    product_active = stripe_field(product, "active")
    _require(
        product_active is True if config.is_current else isinstance(product_active, bool),
        "Pilot Product active state is invalid",
    )
    _require(
        stripe_field(product, "name") == PILOT_PRODUCT_NAME,
        "Pilot Product name mismatch",
    )
    _require(
        bool(stripe_field(product, "livemode")) == config.livemode,
        "Pilot Product livemode mismatch",
    )
    _validate_contract_metadata(product, "Pilot Product")


def _validate_price(price: Any, config: PilotStripeConfig) -> None:
    _require(not isinstance(price, str), "Pilot Price was not expanded")
    _require(stripe_id(price) == config.price_id, "Pilot Price id mismatch")
    price_active = stripe_field(price, "active")
    _require(
        price_active is True if config.is_current else isinstance(price_active, bool),
        "Pilot Price active state is invalid",
    )
    _require(
        bool(stripe_field(price, "livemode")) == config.livemode,
        "Pilot Price livemode mismatch",
    )
    _require_exact_int(
        stripe_field(price, "unit_amount"),
        PILOT_AMOUNT_CENTS,
        "Pilot Price amount mismatch",
    )
    _require(
        str(stripe_field(price, "currency") or "").lower() == PILOT_CURRENCY,
        "Pilot Price currency mismatch",
    )
    _require(stripe_field(price, "type") == "one_time", "Pilot Price is not one-time")
    _require(stripe_field(price, "recurring") is None, "Pilot Price is recurring")
    _validate_product(stripe_field(price, "product"), config)


def _validate_catalog_line_item(line_item: Any, config: PilotStripeConfig) -> None:
    _require_exact_int(
        stripe_field(line_item, "quantity"),
        1,
        "Pilot Payment Link quantity mismatch",
    )
    adjustable = stripe_field(line_item, "adjustable_quantity", {}) or {}
    _require(
        stripe_field(adjustable, "enabled", False) is False,
        "Pilot adjustable quantity must be disabled",
    )
    _validate_price(stripe_field(line_item, "price"), config)


def validate_pilot_provider_contract(
    account: Any,
    payment_link: Any,
    config: PilotStripeConfig,
) -> None:
    """Validate Account -> Payment Link -> Price -> Product without secrets."""
    _require(stripe_id(account) == config.account_id, "Stripe Account id mismatch")
    _require(stripe_field(account, "charges_enabled") is True, "Stripe Account cannot charge")
    _require(
        stripe_field(account, "details_submitted") is True,
        "Stripe Account setup is incomplete",
    )

    _require(
        stripe_id(payment_link) == config.payment_link_id,
        "Pilot Payment Link id mismatch",
    )
    link_active = stripe_field(payment_link, "active")
    _require(
        link_active is True if config.is_current else isinstance(link_active, bool),
        "Pilot Payment Link active state is invalid",
    )
    _require(
        bool(stripe_field(payment_link, "livemode")) == config.livemode,
        "Pilot Payment Link livemode mismatch",
    )
    _require(
        _canonical_payment_link_url(
            stripe_field(payment_link, "url"),
            error_message="Pilot Payment Link URL mismatch",
        )
        == _canonical_payment_link_url(
            config.payment_link_url,
            error_message="Pilot Payment Link URL mismatch",
        ),
        "Pilot Payment Link URL mismatch",
    )
    _require(
        stripe_field(payment_link, "allow_promotion_codes", False) is False,
        "Pilot promotions must be disabled",
    )
    automatic_tax = stripe_field(payment_link, "automatic_tax", {}) or {}
    _require(
        stripe_field(automatic_tax, "enabled", False) is False,
        "Pilot automatic tax must be disabled for the canonical total",
    )
    _require(
        stripe_field(payment_link, "customer_creation") == "always",
        "Pilot Payment Link must create a Stripe Customer",
    )
    _validate_contract_metadata(payment_link, "Pilot Payment Link")
    link_items = stripe_list_data(stripe_field(payment_link, "line_items", {}))
    _require(len(link_items) == 1, "Pilot Payment Link must contain one line item")
    _validate_catalog_line_item(link_items[0], config)


def _validate_checkout_line_item(line_item: Any, config: PilotStripeConfig) -> None:
    _require_exact_int(
        stripe_field(line_item, "quantity"),
        1,
        "Pilot Checkout quantity mismatch",
    )
    _require_exact_int(
        stripe_field(line_item, "amount_subtotal"),
        PILOT_AMOUNT_CENTS,
        "Pilot Checkout line subtotal mismatch",
    )
    _require_exact_int(
        stripe_field(line_item, "amount_total"),
        PILOT_AMOUNT_CENTS,
        "Pilot Checkout line total mismatch",
    )
    _validate_price(stripe_field(line_item, "price"), config)


def _validate_paid_charge(
    charge: Any,
    *,
    config: PilotStripeConfig,
    customer_id: str,
) -> int:
    _require(not isinstance(charge, str), "Pilot Charge was not expanded")
    _require((stripe_id(charge) or "").startswith("ch_"), "Pilot Charge id mismatch")
    _require(bool(stripe_field(charge, "livemode")) == config.livemode, "Pilot Charge livemode mismatch")
    _require(stripe_field(charge, "paid") is True, "Pilot Charge is not paid")
    _require(stripe_field(charge, "refunded") is False, "Pilot Charge is refunded")
    _require(stripe_field(charge, "disputed") is False, "Pilot Charge is disputed")
    _require_exact_int(stripe_field(charge, "amount"), PILOT_AMOUNT_CENTS, "Pilot Charge amount mismatch")
    _require_exact_int(
        stripe_field(charge, "amount_captured"),
        PILOT_AMOUNT_CENTS,
        "Pilot captured amount mismatch",
    )
    _require_exact_int(stripe_field(charge, "amount_refunded", 0), 0, "Pilot refunded amount mismatch")
    _require(
        str(stripe_field(charge, "currency") or "").lower() == PILOT_CURRENCY,
        "Pilot Charge currency mismatch",
    )
    _require(stripe_id(stripe_field(charge, "customer")) == customer_id, "Pilot Charge customer mismatch")

    balance = stripe_field(charge, "balance_transaction")
    _require(not isinstance(balance, str), "Pilot balance transaction was not expanded")
    _require_exact_int(
        stripe_field(balance, "amount"),
        PILOT_AMOUNT_CENTS,
        "Pilot balance gross amount mismatch",
    )
    _require(
        str(stripe_field(balance, "currency") or "").lower() == PILOT_CURRENCY,
        "Pilot balance currency mismatch",
    )
    fee = stripe_field(balance, "fee")
    _require(not isinstance(fee, bool) and isinstance(fee, int) and fee >= 0, "Pilot Stripe fee is unavailable")
    net = stripe_field(balance, "net")
    _require_exact_int(net, PILOT_AMOUNT_CENTS - fee, "Pilot balance net mismatch")
    return fee


def validate_pilot_checkout(
    session: Any,
    line_items_response: Any,
    config: PilotStripeConfig,
    *,
    require_paid: bool,
) -> VerifiedPilotCheckout:
    session_id = stripe_id(session) or ""
    _require(session_id.startswith("cs_"), "Pilot Checkout Session id mismatch")
    _require(is_canonical_payment_link(stripe_field(session, "payment_link"), config), "Pilot Payment Link mismatch")
    _require(stripe_field(session, "mode") == "payment", "Pilot Checkout mode mismatch")
    _require(
        stripe_field(session, "status") in {"open", "complete"},
        "Pilot Checkout status is invalid",
    )
    _require(bool(stripe_field(session, "livemode")) == config.livemode, "Pilot Session livemode mismatch")
    _require(
        str(stripe_field(session, "currency") or "").lower() == PILOT_CURRENCY,
        "Pilot Session currency mismatch",
    )
    _require_exact_int(
        stripe_field(session, "amount_subtotal"),
        PILOT_AMOUNT_CENTS,
        "Pilot Session subtotal mismatch",
    )
    _require_exact_int(
        stripe_field(session, "amount_total"),
        PILOT_AMOUNT_CENTS,
        "Pilot Session total mismatch",
    )
    total_details = stripe_field(session, "total_details", {}) or {}
    for field_name in ("amount_discount", "amount_tax", "amount_shipping"):
        _require_exact_int(
            stripe_field(total_details, field_name, 0),
            0,
            f"Pilot Session {field_name} must be zero",
        )
    _require(not list(stripe_field(session, "discounts", []) or []), "Pilot Session discounts are forbidden")
    _validate_contract_metadata(session, "Pilot Session")

    reference = stripe_field(session, "client_reference_id")
    try:
        request_id = uuid.UUID(str(reference))
    except (TypeError, ValueError) as exc:
        raise _contract_error("Pilot request reference is invalid") from exc

    customer_id = stripe_id(stripe_field(session, "customer")) or ""
    _require(customer_id.startswith("cus_"), "Pilot Stripe Customer is missing")
    details = stripe_field(session, "customer_details", {}) or {}
    customer_email = str(stripe_field(details, "email") or "").strip().lower()
    _require(bool(customer_email), "Pilot customer email is missing")

    line_items = stripe_list_data(line_items_response)
    _require(len(line_items) == 1, "Pilot Checkout must contain one line item")
    line_item = line_items[0]
    _validate_checkout_line_item(line_item, config)

    payment_intent = stripe_field(session, "payment_intent")
    _require(not isinstance(payment_intent, str), "Pilot PaymentIntent was not expanded")
    payment_intent_id = stripe_id(payment_intent) or ""
    _require(payment_intent_id.startswith("pi_"), "Pilot PaymentIntent id mismatch")
    _require(bool(stripe_field(payment_intent, "livemode")) == config.livemode, "Pilot PaymentIntent livemode mismatch")
    _require_exact_int(
        stripe_field(payment_intent, "amount"),
        PILOT_AMOUNT_CENTS,
        "Pilot PaymentIntent amount mismatch",
    )
    _require(
        str(stripe_field(payment_intent, "currency") or "").lower() == PILOT_CURRENCY,
        "Pilot PaymentIntent currency mismatch",
    )
    _require(
        stripe_id(stripe_field(payment_intent, "customer")) == customer_id,
        "Pilot PaymentIntent customer mismatch",
    )

    payment_status = str(stripe_field(session, "payment_status") or "")
    paid = payment_status == "paid"
    stripe_fee: int | None = None
    if require_paid:
        _require(paid, "Pilot Checkout is not paid")
        _require(stripe_field(session, "status") == "complete", "Pilot Checkout is incomplete")
        _require(stripe_field(payment_intent, "status") == "succeeded", "Pilot PaymentIntent did not succeed")
        _require_exact_int(
            stripe_field(payment_intent, "amount_received"),
            PILOT_AMOUNT_CENTS,
            "Pilot received amount mismatch",
        )
        stripe_fee = _validate_paid_charge(
            stripe_field(payment_intent, "latest_charge"),
            config=config,
            customer_id=customer_id,
        )
    else:
        amount_received = stripe_field(payment_intent, "amount_received", 0)
        _require(
            not isinstance(amount_received, bool)
            and isinstance(amount_received, int)
            and 0 <= amount_received <= PILOT_AMOUNT_CENTS,
            "Pilot received amount is invalid",
        )

    return VerifiedPilotCheckout(
        session=session,
        line_item=line_item,
        config=config,
        request_id=request_id,
        customer_id=customer_id,
        customer_email=customer_email,
        payment_intent_id=payment_intent_id,
        paid=paid,
        gross_amount=PILOT_AMOUNT_CENTS,
        stripe_fee_amount=stripe_fee,
        tax_amount=0,
    )


def _validate_event(
    event: Any,
    *,
    event_id: str,
    event_type: str,
    signed_object: Any,
    config: PilotStripeConfig,
) -> Any:
    _require(stripe_id(event) == event_id, "Stripe Event id mismatch")
    _require(stripe_field(event, "type") == event_type, "Stripe Event type mismatch")
    _require(bool(stripe_field(event, "livemode")) == config.livemode, "Stripe Event livemode mismatch")
    event_account = stripe_id(stripe_field(event, "account"))
    _require(event_account in (None, config.account_id), "Stripe Event account mismatch")
    data = stripe_field(event, "data", {}) or {}
    provider_object = stripe_field(data, "object")
    _require(
        stripe_id(provider_object) == stripe_id(signed_object),
        "Stripe Event object mismatch",
    )
    return provider_object


def _validate_signed_checkout_identity(signed: Any, provider: Any) -> None:
    for field_name in (
        "id",
        "payment_link",
        "payment_intent",
        "client_reference_id",
        "livemode",
        "currency",
        "amount_subtotal",
        "amount_total",
    ):
        signed_value = stripe_field(signed, field_name)
        provider_value = stripe_field(provider, field_name)
        if field_name in {"id", "payment_link", "payment_intent"}:
            signed_value = stripe_id(signed_value)
            provider_value = stripe_id(provider_value)
        _require(signed_value == provider_value, f"Signed Pilot {field_name} mismatch")


async def _bounded_stripe_call(call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    retryable = (stripe.error.APIConnectionError, stripe.error.RateLimitError, TimeoutError)
    for attempt in range(PILOT_PROVIDER_MAX_ATTEMPTS):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(call, *args, **kwargs),
                timeout=PILOT_PROVIDER_TIMEOUT_SECONDS,
            )
        except retryable as exc:
            if attempt + 1 >= PILOT_PROVIDER_MAX_ATTEMPTS:
                raise PilotStripeProviderUnavailable(
                    "Stripe verification timed out or was rate limited"
                ) from exc
            await asyncio.sleep(0.2 * (attempt + 1))
        except stripe.error.StripeError as exc:
            raise PilotStripeProviderUnavailable(
                "Stripe verification was unavailable"
            ) from exc
    raise PilotStripeProviderUnavailable("Stripe verification was unavailable")


async def retrieve_pilot_event(event_id: str) -> Any:
    return await _bounded_stripe_call(
        stripe.Event.retrieve,
        event_id,
        stripe_version=PILOT_STRIPE_API_VERSION,
    )


async def retrieve_pilot_account() -> Any:
    return await _bounded_stripe_call(
        stripe.Account.retrieve,
        stripe_version=PILOT_STRIPE_API_VERSION,
    )


async def retrieve_pilot_payment_link(payment_link_id: str) -> Any:
    return await _bounded_stripe_call(
        stripe.PaymentLink.retrieve,
        payment_link_id,
        expand=["line_items.data.price.product"],
        stripe_version=PILOT_STRIPE_API_VERSION,
    )


async def retrieve_pilot_checkout_session(session_id: str) -> Any:
    return await _bounded_stripe_call(
        stripe.checkout.Session.retrieve,
        session_id,
        expand=["payment_intent.latest_charge.balance_transaction"],
        stripe_version=PILOT_STRIPE_API_VERSION,
    )


async def retrieve_pilot_line_items(session_id: str) -> Any:
    return await _bounded_stripe_call(
        stripe.checkout.Session.list_line_items,
        session_id,
        limit=2,
        expand=["data.price.product"],
        stripe_version=PILOT_STRIPE_API_VERSION,
    )


async def verify_pilot_checkout_session(session_id: str) -> VerifiedPilotCheckout:
    account, session, line_items = await asyncio.gather(
        retrieve_pilot_account(),
        retrieve_pilot_checkout_session(session_id),
        retrieve_pilot_line_items(session_id),
    )
    config = find_authorized_pilot_stripe_config(stripe_field(session, "payment_link"))
    _require(config is not None, "Pilot Payment Link is not authorized")
    payment_link = await retrieve_pilot_payment_link(config.payment_link_id)
    validate_pilot_provider_contract(account, payment_link, config)
    return validate_pilot_checkout(
        session,
        line_items,
        config,
        require_paid=True,
    )


async def verify_pilot_checkout_event(
    event_id: str,
    event_type: str,
    signed_session: Any,
) -> VerifiedPilotCheckout:
    config = find_authorized_pilot_stripe_config(
        stripe_field(signed_session, "payment_link")
    )
    _require(event_type in PILOT_CHECKOUT_EVENT_TYPES, "Unsupported Pilot event type")
    _require(config is not None, "Pilot Payment Link is not authorized")
    event, account, payment_link = await asyncio.gather(
        retrieve_pilot_event(event_id),
        retrieve_pilot_account(),
        retrieve_pilot_payment_link(config.payment_link_id),
    )
    provider_session = _validate_event(
        event,
        event_id=event_id,
        event_type=event_type,
        signed_object=signed_session,
        config=config,
    )
    _validate_signed_checkout_identity(signed_session, provider_session)
    validate_pilot_provider_contract(account, payment_link, config)
    session_id = stripe_id(provider_session) or ""
    session, line_items = await asyncio.gather(
        retrieve_pilot_checkout_session(session_id),
        retrieve_pilot_line_items(session_id),
    )
    _require(stripe_id(session) == session_id, "Pilot Session retrieval mismatch")
    require_paid = event_type == "checkout.session.async_payment_succeeded" or (
        event_type == "checkout.session.completed"
        and stripe_field(session, "payment_status") == "paid"
    )
    if event_type == "checkout.session.async_payment_failed":
        _require(
            stripe_field(session, "payment_status") != "paid",
            "Failed Pilot event contradicts paid provider state",
        )
    return validate_pilot_checkout(
        session,
        line_items,
        config,
        require_paid=require_paid,
    )


async def verify_pilot_reversal_event(
    event_id: str,
    event_type: str,
    signed_object: Any,
) -> tuple[Any, PilotStripeConfig]:
    config = load_pilot_stripe_config()
    _require(event_type in PILOT_REVERSAL_EVENT_TYPES, "Unsupported Pilot reversal event")
    event, account = await asyncio.gather(
        retrieve_pilot_event(event_id),
        retrieve_pilot_account(),
    )
    provider_object = _validate_event(
        event,
        event_id=event_id,
        event_type=event_type,
        signed_object=signed_object,
        config=config,
    )
    _require(stripe_id(account) == config.account_id, "Stripe Account id mismatch")
    _require(stripe_field(account, "charges_enabled") is True, "Stripe Account cannot charge")
    return provider_object, config
