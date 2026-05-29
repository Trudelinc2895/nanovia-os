"""
stripe/setup_stripe.py
Nanovia OS — Stripe bootstrap (run once, idempotent)

Usage:
    python stripe/setup_stripe.py

Creates / reuses:
  - Products & Prices for Starter ($29/mo), Pro ($79/mo, $790/yr) and Business ($149/mo, $1,490/yr)
  - API / storage / credits add-on prices
  - 10 individual module prices
  - Credit pack price
  - Webhook endpoint
  - Customer portal configuration

Outputs: stripe/stripe_ids.json, stripe/sandbox/stripe-output.sandbox.json + .env snippet to copy
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

for env_path in (REPO_ROOT / ".env", REPO_ROOT / ".env.sandbox", REPO_ROOT / ".env.production", REPO_ROOT / ".env.staging"):
    if env_path.is_file():
        load_dotenv(env_path, override=False)
load_dotenv(override=False)

try:
    import stripe
except ImportError:
    raise SystemExit("pip install stripe python-dotenv")

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
stripe_prefix = "sk" + "_"
stripe_test_prefix = "sk" + "_test_"
assert stripe.api_key.startswith(stripe_prefix), "Invalid STRIPE_SECRET_KEY"

MODE = "TEST" if stripe.api_key.startswith(stripe_test_prefix) else "LIVE"
DOMAIN = os.getenv("DOMAIN", "nanovia.ca").strip()


def _public_origin() -> str:
    explicit = os.getenv("PUBLIC_WEB_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    domain = DOMAIN[4:] if DOMAIN.startswith("api.") else DOMAIN
    return f"https://{domain}"


def _api_origin() -> str:
    explicit = os.getenv("API_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    if DOMAIN.startswith("api."):
        return f"https://{DOMAIN}"
    return f"https://api.{DOMAIN}"


def _webhook_url() -> str:
    explicit = os.getenv("STRIPE_WEBHOOK_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    if os.getenv("APP_ENV", "").strip().lower() == "sandbox":
        return f"{_api_origin()}/stripe/webhook"
    return f"{_api_origin()}/api/v1/billing/webhook"


PUBLIC_WEB_URL = _public_origin()
API_BASE_URL = _api_origin()
WEBHOOK_URL = _webhook_url()

print(f"[stripe-setup] mode={MODE}  domain={DOMAIN}  api={API_BASE_URL}")

# ─── Plan prices ──────────────────────────────────────────────────────────────
PLANS = [
    {
        "key": "starter",
        "name": "Nanovia Starter",
        "usd_monthly": 2900,
        "usd_yearly": 2900 * 12,
        "description": "Core platform, billing, support base, and conservative AI sandbox guardrails",
    },
    {
        "key": "pro",
        "name": "Nanovia Pro",
        "usd_monthly": 7900,   # $79.00/mo
        "usd_yearly": 79000,   # $790.00/yr  (saves ~$158)
        "description": "5 AI modules — 1,000 messages/month — Priority support",
    },
    {
        "key": "business",
        "name": "Nanovia Business",
        "usd_monthly": 14900,  # $149.00/mo
        "usd_yearly": 149000,  # $1,490.00/yr  (saves ~$298)
        "description": "All 10 AI modules — Unlimited messages — Dedicated support",
    },
]

# ─── Individual module prices ─────────────────────────────────────────────────
MODULES = [
    {"key": "operator",   "name": "AI Personal Operator",      "usd_monthly": 1900},
    {"key": "content",    "name": "Content Cloner Engine",      "usd_monthly": 1500},
    {"key": "micro_saas", "name": "Micro-SaaS Builder",         "usd_monthly": 2900},
    {"key": "ghost",      "name": "Ghost Automation Agency",    "usd_monthly": 3900},
    {"key": "decision",   "name": "AI Decision Engine",         "usd_monthly": 1900},
    {"key": "knowledge",  "name": "Knowledge Weapon System",    "usd_monthly": 1500},
    {"key": "leverage",   "name": "Digital Leverage Engine",    "usd_monthly": 1900},
    {"key": "reverse",    "name": "Reverse Engineering Module", "usd_monthly": 2500},
    {"key": "offer",      "name": "Offer Generator",            "usd_monthly": 1500},
    {"key": "execution",  "name": "Execution Service",          "usd_monthly": 2900},
]

CREDIT_PACK = {
    "name": "Nanovia Credits Pack (100 crédits)",
    "usd_cents": 999,
    "credits": 100,
    "description": "Pack de 100 crédits IA — valable sans expiration",
}

ADDONS = [
    {
        "key": "api_calls_500",
        "name": "Nanovia API Pack (500 calls)",
        "usd_cents": 500,
        "description": "+500 API calls for the current month",
        "env_key": "STRIPE_PRICE_ADDON_API_PACK",
        "metadata": {"grants": '{"api_calls_extra": 500}'},
    },
    {
        "key": "storage_10gb",
        "name": "Nanovia Storage Pack (10 GB)",
        "usd_cents": 500,
        "description": "+10 GB storage add-on",
        "env_key": "STRIPE_PRICE_ADDON_STORAGE_10GB",
        "metadata": {"grants": '{"storage_gb_extra": 10}'},
    },
    {
        "key": "credits_50",
        "name": "Nanovia Credit Pack (50 credits)",
        "usd_cents": 400,
        "description": "50 overage credits (1 credit = 1 extra message)",
        "env_key": "STRIPE_PRICE_CREDITS_PACK",
        "metadata": {"grants": '{"credits": 50}'},
    },
]

WEBHOOK_EVENTS = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "customer.subscription.trial_will_end",
    "customer.updated",
    "payment_method.attached",
]
SHOW_WEBHOOK_SECRET = os.getenv("STRIPE_SHOW_WEBHOOK_SECRET", "").strip().lower() in {"1", "true", "yes"}

MODULE_ENV_MAP = {
    "operator": "STRIPE_PRICE_MODULE_OPERATOR",
    "content": "STRIPE_PRICE_MODULE_CONTENT",
    "micro_saas": "STRIPE_PRICE_MODULE_MICRO_SAAS",
    "ghost": "STRIPE_PRICE_MODULE_GHOST",
    "decision": "STRIPE_PRICE_MODULE_DECISION",
    "knowledge": "STRIPE_PRICE_MODULE_KNOWLEDGE",
    "leverage": "STRIPE_PRICE_MODULE_LEVERAGE",
    "reverse": "STRIPE_PRICE_MODULE_REVERSE",
    "offer": "STRIPE_PRICE_MODULE_OFFER",
    "execution": "STRIPE_PRICE_MODULE_EXECUTION",
}


def _merge_metadata(existing: dict[str, Any] | None, updates: dict[str, Any]) -> dict[str, str]:
    merged = {str(k): str(v) for k, v in (existing or {}).items()}
    for key, value in updates.items():
        merged[str(key)] = str(value)
    return merged


def _find_existing_product(*, metadata_key: str, metadata_value: str, name: str):
    existing = stripe.Product.search(query=f'metadata["{metadata_key}"]:"{metadata_value}"').data
    if existing:
        return existing[0], "metadata"

    for product in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        if product.name == name:
            return product, "name"
    return None, None


def _ensure_product_metadata(product, metadata: dict[str, str]) -> None:
    current = {str(k): str(v) for k, v in (product.metadata or {}).items()}
    if all(current.get(key) == value for key, value in metadata.items()):
        return
    stripe.Product.modify(product.id, metadata=_merge_metadata(current, metadata))


def _find_existing_price(*, product_id: str, unit_amount: int, interval: str | None) -> Any | None:
    for price in stripe.Price.list(product=product_id, active=True, limit=100).auto_paging_iter():
        if price.unit_amount != unit_amount or price.currency != "usd":
            continue
        if interval is None and not price.recurring:
            return price
        if interval is not None and price.recurring and price.recurring.interval == interval:
            return price
    return None


def upsert_product_and_price(plan: dict) -> dict:
    product, source = _find_existing_product(
        metadata_key="plan_key",
        metadata_value=plan["key"],
        name=plan["name"],
    )
    if product:
        _ensure_product_metadata(product, {"plan_key": plan["key"], "product_type": "plan"})
        print(f"  [exists:{source}] product {product.id} ({plan['name']})")
    else:
        product = stripe.Product.create(
            name=plan["name"],
            description=plan["description"],
            metadata={"plan_key": plan["key"], "product_type": "plan"},
        )
        print(f"  [created] product {product.id} ({plan['name']})")

    # Monthly price
    price_monthly = _find_existing_price(product_id=product.id, unit_amount=plan["usd_monthly"], interval="month")
    if price_monthly:
        print(f"  [exists] monthly {price_monthly.id} (${plan['usd_monthly']/100:.2f}/mo)")
    else:
        price_monthly = stripe.Price.create(
            product=product.id,
            unit_amount=plan["usd_monthly"],
            currency="usd",
            recurring={"interval": "month"},
            metadata={"plan_key": plan["key"], "interval": "monthly"},
        )
        print(f"  [created] monthly {price_monthly.id} (${plan['usd_monthly']/100:.2f}/mo)")

    # Yearly price
    price_yearly = _find_existing_price(product_id=product.id, unit_amount=plan["usd_yearly"], interval="year")
    if price_yearly:
        print(f"  [exists] yearly  {price_yearly.id} (${plan['usd_yearly']/100:.2f}/yr)")
    else:
        price_yearly = stripe.Price.create(
            product=product.id,
            unit_amount=plan["usd_yearly"],
            currency="usd",
            recurring={"interval": "year"},
            metadata={"plan_key": plan["key"], "interval": "yearly"},
        )
        print(f"  [created] yearly  {price_yearly.id} (${plan['usd_yearly']/100:.2f}/yr)")

    return {
        "product_id": product.id,
        "price_monthly_id": price_monthly.id,
        "price_yearly_id": price_yearly.id,
    }


def upsert_module_price(mod: dict[str, Any]) -> str:
    """Create a recurring monthly price for a single module."""
    product, source = _find_existing_product(
        metadata_key="module_key",
        metadata_value=mod["key"],
        name=f"Nanovia — {mod['name']}",
    )
    if product:
        _ensure_product_metadata(product, {"module_key": mod["key"], "product_type": "module"})
        print(f"  [exists:{source}] module product {product.id} ({mod['name']})")
    else:
        product = stripe.Product.create(
            name=f"Nanovia — {mod['name']}",
            description=f"Individual module subscription: {mod['name']}",
            metadata={"module_key": mod["key"], "product_type": "module"},
        )
        print(f"  [created] module product {product.id} ({mod['name']})")

    price = _find_existing_price(product_id=product.id, unit_amount=mod["usd_monthly"], interval="month")
    if price:
        print(f"  [exists] module price {price.id} (${mod['usd_monthly']/100:.2f}/mo)")
    else:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=mod["usd_monthly"],
            currency="usd",
            recurring={"interval": "month"},
            metadata={"module_key": mod["key"]},
        )
        print(f"  [created] module price {price.id} (${mod['usd_monthly']/100:.2f}/mo)")

    return price.id


def upsert_one_time_price(
    *,
    product_key: str,
    name: str,
    description: str,
    usd_cents: int,
    metadata: dict[str, str] | None = None,
) -> dict[str, str]:
    product, source = _find_existing_product(
        metadata_key="product_key",
        metadata_value=product_key,
        name=name,
    )
    if product:
        _ensure_product_metadata(product, {"product_key": product_key, **(metadata or {})})
        print(f"  [exists:{source}] one-time product {product.id} ({name})")
    else:
        product = stripe.Product.create(
            name=name,
            description=description,
            metadata={"product_key": product_key, **(metadata or {})},
        )
        print(f"  [created] one-time product {product.id} ({name})")

    price = _find_existing_price(product_id=product.id, unit_amount=usd_cents, interval=None)
    if price:
        print(f"  [exists] one-time price {price.id} (${usd_cents/100:.2f})")
    else:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=usd_cents,
            currency="usd",
            metadata={"product_key": product_key, **(metadata or {})},
        )
        print(f"  [created] one-time price {price.id} (${usd_cents/100:.2f})")

    return {"product_id": product.id, "price_id": price.id}


def upsert_credit_pack(pack: dict[str, Any]) -> dict[str, str]:
    return upsert_one_time_price(
        product_key="credit_pack",
        name=pack["name"],
        description=pack["description"],
        usd_cents=pack["usd_cents"],
        metadata={"credits": str(pack["credits"])},
    )


def setup_webhook() -> stripe.WebhookEndpoint:
    existing = [w for w in stripe.WebhookEndpoint.list().data if w.url == WEBHOOK_URL]
    if existing:
        wh = existing[0]
        current_events = set(getattr(wh, "enabled_events", []) or [])
        required_events = set(WEBHOOK_EVENTS)
        if current_events != required_events:
            wh = stripe.WebhookEndpoint.modify(
                wh.id,
                enabled_events=WEBHOOK_EVENTS,
                description="Nanovia OS — production webhook",
            )
            print(f"  [updated] webhook {wh.id} -> {WEBHOOK_URL}")
        else:
            print(f"  [exists] webhook {wh.id} -> {WEBHOOK_URL}")
        return wh
    wh = stripe.WebhookEndpoint.create(
        url=WEBHOOK_URL,
        enabled_events=WEBHOOK_EVENTS,
        description="Nanovia OS — production webhook",
    )
    print(f"  [created] webhook {wh.id} -> {WEBHOOK_URL}")
    if SHOW_WEBHOOK_SECRET:
        print(f"  *** STRIPE_WEBHOOK_SECRET={wh.secret} ***")
    else:
        print("  *** STRIPE_WEBHOOK_SECRET hidden (set STRIPE_SHOW_WEBHOOK_SECRET=1 to reveal once) ***")
    return wh


def setup_portal(plan_results: dict[str, dict[str, str]]) -> stripe.billing_portal.Configuration:
    products = [
        {
            "product": cfg["product_id"],
            "prices": [cfg["price_monthly_id"], cfg["price_yearly_id"]],
        }
        for cfg in plan_results.values()
    ]
    payload = {
        "business_profile": {
            "headline": "Gérez votre abonnement Nanovia",
            "privacy_policy_url": f"{PUBLIC_WEB_URL}/privacy",
            "terms_of_service_url": f"{PUBLIC_WEB_URL}/terms",
        },
        "features": {
            "subscription_cancel": {"enabled": True, "mode": "at_period_end"},
            "subscription_update": {
                "enabled": True,
                "default_allowed_updates": ["price", "quantity", "promotion_code"],
                "proration_behavior": "create_prorations",
                "products": products,
            },
            "payment_method_update": {"enabled": True},
            "invoice_history": {"enabled": True},
        },
    }
    configs = stripe.billing_portal.Configuration.list(active=True).data
    if configs:
        cfg = stripe.billing_portal.Configuration.modify(configs[0].id, **payload)
        print(f"  [updated] portal config {cfg.id}")
        return cfg
    cfg = stripe.billing_portal.Configuration.create(**payload)
    print(f"  [created] portal config {cfg.id}")
    return cfg


def main():
    print("\n[1/6] Plan Products & Prices")
    plan_results = {}
    for plan in PLANS:
        plan_results[plan["key"]] = upsert_product_and_price(plan)

    print("\n[2/6] Add-on Prices")
    addon_results = {}
    for addon in ADDONS:
        addon_results[addon["key"]] = upsert_one_time_price(
            product_key=addon["key"],
            name=addon["name"],
            description=addon["description"],
            usd_cents=addon["usd_cents"],
            metadata=addon["metadata"],
        )

    print("\n[3/6] Individual Module Prices")
    module_results = {}
    for mod in MODULES:
        module_results[mod["key"]] = upsert_module_price(mod)

    print("\n[4/6] Credit Pack")
    credit_pack = upsert_credit_pack(CREDIT_PACK)

    print("\n[5/6] Webhook")
    wh = setup_webhook()

    print("\n[6/6] Customer Portal")
    setup_portal(plan_results)

    env_values = {
        "STRIPE_PRICE_STARTER_MONTHLY_ID": plan_results["starter"]["price_monthly_id"],
        "STRIPE_PRICE_PRO_MONTHLY_ID": plan_results["pro"]["price_monthly_id"],
        "STRIPE_PRICE_PRO_YEARLY_ID": plan_results["pro"]["price_yearly_id"],
        "STRIPE_PRICE_BUSINESS_MONTHLY_ID": plan_results["business"]["price_monthly_id"],
        "STRIPE_PRICE_BUSINESS_YEARLY_ID": plan_results["business"]["price_yearly_id"],
        "STRIPE_CREDIT_PRICE_ID": credit_pack["price_id"],
        "STRIPE_PRICE_ADDON_API_PACK": addon_results["api_calls_500"]["price_id"],
        "STRIPE_PRICE_ADDON_STORAGE_10GB": addon_results["storage_10gb"]["price_id"],
        "STRIPE_PRICE_CREDITS_PACK": addon_results["credits_50"]["price_id"],
    }
    for slug, env_key in MODULE_ENV_MAP.items():
        env_values[env_key] = module_results[slug]

    # ── Save IDs to file ──────────────────────────────────────────────────────
    output = {
        "mode": MODE,
        "domain": DOMAIN,
        "public_web_url": PUBLIC_WEB_URL,
        "api_base_url": API_BASE_URL,
        "webhook_url": WEBHOOK_URL,
        "generated_at": datetime.now(UTC).isoformat(),
        "plans": plan_results,
        "addons": addon_results,
        "modules": module_results,
        "credit_pack": {
            "product_id": credit_pack["product_id"],
            "price_id": credit_pack["price_id"],
            "credits": CREDIT_PACK["credits"],
        },
        "credit_price_id": credit_pack["price_id"],
        "products": {
            "STRIPE_PRODUCT_STARTER": plan_results["starter"]["product_id"],
            "STRIPE_PRODUCT_PRO": plan_results["pro"]["product_id"],
            "STRIPE_PRODUCT_BUSINESS": plan_results["business"]["product_id"]
        },
        "webhook": {"id": wh.id, "url": WEBHOOK_URL},
        "webhook_id": wh.id,
        "env": env_values,
    }
    output_path = SCRIPT_DIR / "stripe_ids.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    sandbox_output_path = SCRIPT_DIR / "sandbox" / "stripe-output.sandbox.json"
    sandbox_output_path.parent.mkdir(parents=True, exist_ok=True)
    with sandbox_output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print("\n" + "=" * 60)
    print(f"✅  {output_path.relative_to(REPO_ROOT)} saved")
    print(f"✅  {sandbox_output_path.relative_to(REPO_ROOT)} saved")
    print("=" * 60)
    print("\n--- COPY THESE TO YOUR .env ---\n")
    for env_key, value in env_values.items():
        print(f"{env_key}={value}")

    print("\n--- ALSO ADD ---")
    print(f"# Stripe webhook endpoint: {WEBHOOK_URL}")
    print("# Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    print("TOTP_ENCRYPTION_KEY=<generated_key>")
    print("=" * 60)


if __name__ == "__main__":
    main()
