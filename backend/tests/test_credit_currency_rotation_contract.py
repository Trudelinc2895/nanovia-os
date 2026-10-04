from pathlib import Path


def test_historical_credit_currency_is_not_tied_to_current_catalog_currency():
    source = (
        Path(__file__).resolve().parents[1]
        / "api"
        / "services"
        / "billing_service.py"
    ).read_text(encoding="utf-8")
    start = source.index("def validate_credit_checkout_contract(")
    end = source.index("async def verify_credit_checkout_session(", start)
    contract = source[start:end]

    assert "current_currency = current_contract.currency" not in contract
    assert "currency != current_currency" not in contract
    assert 'stripe_field(provider_session, "currency") != currency' in contract
    assert 'stripe_field(payment_intent, "currency") != currency' in contract
