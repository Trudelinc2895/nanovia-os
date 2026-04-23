"""
stripe/setup_stripe.py
Nanovia OS — Stripe bootstrap (run once, idempotent)

Usage:
    python stripe/setup_stripe.py

Creates / reuses:
  - Products & Prices for Pro ($79/mo, $790/yr) and Business ($149/mo, $1,490/yr)
  - 10 individual module prices
  - Credit pack price
  - Webhook endpoint
  - Customer portal configuration

Outputs: stripe/stripe_ids.json + .env snippet to copy
"""
import os, json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

try:
    import stripe
except ImportError:
    raise SystemExit("pip install stripe python-dotenv")

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
assert stripe.api_key.startswith("sk_"), "Invalid STRIPE_SECRET_KEY"

MODE = "TEST" if stripe.api_key.startswith("sk_test_") else "LIVE"
DOMAIN = os.getenv("DOMAIN", "nanovia.ca")
print(f"[stripe-setup] mode={MODE}  domain={DOMAIN}")

# ─── Plan prices ──────────────────────────────────────────────────────────────
PLANS = [
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

WEBHOOK_EVENTS = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "customer.subscription.trial_will_end",
]


def upsert_product_and_price(plan: dict) -> dict:
    existing = stripe.Product.search(query=f'metadata["plan_key"]:"{plan["key"]}"').data
    if existing:
        product = existing[0]
        print(f"  [exists] product {product.id} ({plan['name']})")
    else:
        product = stripe.Product.create(
            name=plan["name"],
            description=plan["description"],
            metadata={"plan_key": plan["key"], "product_type": "plan"},
        )
        print(f"  [created] product {product.id} ({plan['name']})")

    existing_prices = stripe.Price.list(product=product.id, active=True).data

    # Monthly price
    monthly = [p for p in existing_prices
               if p.recurring and p.recurring.interval == "month"
               and p.unit_amount == plan["usd_monthly"]]
    if monthly:
        price_monthly = monthly[0]
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
    yearly = [p for p in existing_prices
              if p.recurring and p.recurring.interval == "year"
              and p.unit_amount == plan["usd_yearly"]]
    if yearly:
        price_yearly = yearly[0]
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


def upsert_module_price(mod: dict) -> str:
    """Create a recurring monthly price for a single module."""
    meta_key = f"module_{mod['key']}"
    existing = stripe.Product.search(query=f'metadata["module_key"]:"{mod["key"]}"').data
    if existing:
        product = existing[0]
        print(f"  [exists] module product {product.id} ({mod['name']})")
    else:
        product = stripe.Product.create(
            name=f"Nanovia — {mod['name']}",
            description=f"Individual module subscription: {mod['name']}",
            metadata={"module_key": mod["key"], "product_type": "module"},
        )
        print(f"  [created] module product {product.id} ({mod['name']})")

    existing_prices = stripe.Price.list(product=product.id, active=True).data
    monthly = [p for p in existing_prices
               if p.recurring and p.recurring.interval == "month"
               and p.unit_amount == mod["usd_monthly"]]
    if monthly:
        price = monthly[0]
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


def upsert_credit_pack(pack: dict) -> str:
    existing = stripe.Product.search(query='metadata["product_key"]:"credit_pack"').data
    if existing:
        product = existing[0]
    else:
        product = stripe.Product.create(
            name=pack["name"],
            description=pack["description"],
            metadata={"product_key": "credit_pack", "credits": str(pack["credits"])},
        )
        print(f"  [created] credit pack product {product.id}")

    prices = stripe.Price.list(product=product.id, active=True).data
    one_time = [p for p in prices if not p.recurring and p.unit_amount == pack["usd_cents"]]
    if one_time:
        price = one_time[0]
        print(f"  [exists] credit pack price {price.id} (${pack['usd_cents']/100:.2f})")
    else:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=pack["usd_cents"],
            currency="usd",
            metadata={"product_key": "credit_pack", "credits": str(pack["credits"])},
        )
        print(f"  [created] credit pack price {price.id} (${pack['usd_cents']/100:.2f})")

    return price.id


def setup_webhook() -> stripe.WebhookEndpoint:
    url = f"https://{DOMAIN}/api/v1/billing/webhook"
    existing = [w for w in stripe.WebhookEndpoint.list().data if w.url == url]
    if existing:
        wh = existing[0]
        print(f"  [exists] webhook {wh.id} -> {url}")
        return wh
    wh = stripe.WebhookEndpoint.create(
        url=url,
        enabled_events=WEBHOOK_EVENTS,
        description="Nanovia OS — production webhook",
    )
    print(f"  [created] webhook {wh.id} -> {url}")
    print(f"  *** STRIPE_WEBHOOK_SECRET={wh.secret} ***")
    return wh


def setup_portal() -> stripe.billing_portal.Configuration:
    configs = stripe.billing_portal.Configuration.list(active=True).data
    if configs:
        print(f"  [exists] portal config {configs[0].id}")
        return configs[0]
    cfg = stripe.billing_portal.Configuration.create(
        business_profile={
            "headline": "Gérez votre abonnement Nanovia",
            "privacy_policy_url": f"https://{DOMAIN}/privacy",
            "terms_of_service_url": f"https://{DOMAIN}/terms",
        },
        features={
            "subscription_cancel": {"enabled": True, "mode": "at_period_end"},
            "subscription_update": {
                "enabled": True,
                "default_allowed_updates": ["price", "quantity", "promotion_code"],
                "proration_behavior": "create_prorations",
                "products": [],  # filled dynamically below
            },
            "payment_method_update": {"enabled": True},
            "invoice_history": {"enabled": True},
        },
    )
    print(f"  [created] portal config {cfg.id}")
    return cfg


def main():
    print("\n[1/5] Plan Products & Prices")
    plan_results = {}
    for plan in PLANS:
        plan_results[plan["key"]] = upsert_product_and_price(plan)

    print("\n[2/5] Individual Module Prices")
    module_results = {}
    for mod in MODULES:
        module_results[mod["key"]] = upsert_module_price(mod)

    print("\n[3/5] Credit Pack")
    credit_price_id = upsert_credit_pack(CREDIT_PACK)

    print("\n[4/5] Webhook")
    wh = setup_webhook()

    print("\n[5/5] Customer Portal")
    setup_portal()

    # ── Save IDs to file ──────────────────────────────────────────────────────
    os.makedirs("stripe", exist_ok=True)
    output = {
        "mode": MODE,
        "domain": DOMAIN,
        "generated_at": datetime.utcnow().isoformat(),
        "plans": plan_results,
        "modules": module_results,
        "credit_price_id": credit_price_id,
        "webhook_id": wh.id,
    }
    with open("stripe/stripe_ids.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\n" + "=" * 60)
    print("✅  stripe/stripe_ids.json saved")
    print("=" * 60)
    print("\n--- COPY THESE TO YOUR .env ---\n")

    if plan_results.get("pro"):
        print(f"STRIPE_PRICE_PRO_MONTHLY_ID={plan_results['pro']['price_monthly_id']}")
        print(f"STRIPE_PRICE_PRO_YEARLY_ID={plan_results['pro']['price_yearly_id']}")
    if plan_results.get("business"):
        print(f"STRIPE_PRICE_BUSINESS_MONTHLY_ID={plan_results['business']['price_monthly_id']}")
        print(f"STRIPE_PRICE_BUSINESS_YEARLY_ID={plan_results['business']['price_yearly_id']}")

    print(f"STRIPE_CREDIT_PRICE_ID={credit_price_id}")
    print()

    env_map = {
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
    for slug, env_key in env_map.items():
        price_id = module_results.get(slug, "NOT_CREATED")
        print(f"{env_key}={price_id}")

    print("\n--- ALSO ADD ---")
    print("# Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    print("TOTP_ENCRYPTION_KEY=<generated_key>")
    print("=" * 60)


if __name__ == "__main__":
    main()
