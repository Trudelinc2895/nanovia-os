import logging

from api import main


def test_production_allows_partial_plan_catalog(monkeypatch, caplog):
    monkeypatch.setattr(main.settings, "APP_ENV", "production")
    monkeypatch.setattr(main.settings, "STRIPE_PRICE_PRO_MONTHLY_ID", "price_pro_monthly")
    monkeypatch.setattr(main.settings, "STRIPE_PRICE_PRO_YEARLY_ID", "")
    monkeypatch.setattr(main.settings, "STRIPE_PRICE_BUSINESS_MONTHLY_ID", "price_business_monthly")
    monkeypatch.setattr(main.settings, "STRIPE_PRICE_BUSINESS_YEARLY_ID", "")
    for module_key in (
        "STRIPE_PRICE_MODULE_OPERATOR",
        "STRIPE_PRICE_MODULE_CONTENT",
        "STRIPE_PRICE_MODULE_MICRO_SAAS",
        "STRIPE_PRICE_MODULE_GHOST",
        "STRIPE_PRICE_MODULE_DECISION",
        "STRIPE_PRICE_MODULE_KNOWLEDGE",
        "STRIPE_PRICE_MODULE_LEVERAGE",
        "STRIPE_PRICE_MODULE_REVERSE",
        "STRIPE_PRICE_MODULE_OFFER",
        "STRIPE_PRICE_MODULE_EXECUTION",
    ):
        monkeypatch.setattr(main.settings, module_key, "")

    with caplog.at_level(logging.WARNING):
        main._validate_billing_startup_config()

    assert "Missing Stripe plan price IDs" in caplog.text


def test_production_rejects_empty_plan_catalog(monkeypatch):
    monkeypatch.setattr(main.settings, "APP_ENV", "production")
    monkeypatch.setattr(main.settings, "STRIPE_PRICE_PRO_MONTHLY_ID", "")
    monkeypatch.setattr(main.settings, "STRIPE_PRICE_PRO_YEARLY_ID", "")
    monkeypatch.setattr(main.settings, "STRIPE_PRICE_BUSINESS_MONTHLY_ID", "")
    monkeypatch.setattr(main.settings, "STRIPE_PRICE_BUSINESS_YEARLY_ID", "")

    try:
        main._validate_billing_startup_config()
    except RuntimeError as exc:
        assert "No Stripe plan price IDs configured in production" in str(exc)
    else:
        raise AssertionError("Expected production startup validation to fail")
