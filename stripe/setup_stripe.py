"""
stripe/setup_stripe.py
KT Monetization OS — Stripe bootstrap (run once)
Usage: python stripe/setup_stripe.py
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

MODE = "TEST" if stripe.api_key.startswith("stripe_test_") else "LIVE"
DOMAIN = os.getenv("DOMAIN", "tkverse.ca")
print(f"[stripe-setup] mode={MODE}  domain={DOMAIN}")


PLANS = [
    {"key": "starter",  "name": "KT Starter",  "usd_cents": 0,     "description": "Accès basique gratuit"},
    {"key": "pro",      "name": "KT Pro",       "usd_cents": 4900,  "description": "Modules 1-5 complets"},
    {"key": "business", "name": "KT Business",  "usd_cents": 14900, "description": "Tous les modules 1-10"},
]

WEBHOOK_EVENTS = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "customer.created",
    "customer.deleted",
]


def upsert_product_and_price(plan: dict) -> dict:
    # Search existing product by metadata key
    existing = stripe.Product.search(query=f'metadata["plan_key"]:"{plan["key"]}"').data
    if existing:
        product = existing[0]
        print(f"  [exists] product {product.id} ({plan['name']})")
    else:
        product = stripe.Product.create(
            name=plan["name"],
            description=plan["description"],
            metadata={"plan_key": plan["key"]},
        )
        print(f"  [created] product {product.id} ({plan['name']})")

    if plan["usd_cents"] == 0:
        return {"product_id": product.id, "price_id": "free"}

    # Search existing active price
    prices = stripe.Price.list(product=product.id, active=True).data
    monthly = [p for p in prices if p.recurring and p.recurring.interval == "month"]
    if monthly:
        price = monthly[0]
        print(f"  [exists] price {price.id} (${plan['usd_cents']/100}/mo)")
    else:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=plan["usd_cents"],
            currency="usd",
            recurring={"interval": "month"},
            metadata={"plan_key": plan["key"]},
        )
        print(f"  [created] price {price.id} (${plan['usd_cents']/100}/mo)")

    return {"product_id": product.id, "price_id": price.id}


def setup_webhook() -> stripe.WebhookEndpoint:
    url = f"https://{DOMAIN}/api/billing/webhook"
    existing = [w for w in stripe.WebhookEndpoint.list().data if w.url == url]
    if existing:
        wh = existing[0]
        print(f"  [exists] webhook {wh.id} -> {url}")
        return wh
    wh = stripe.WebhookEndpoint.create(
        url=url,
        enabled_events=WEBHOOK_EVENTS,
        description="KT Monetization OS webhook",
    )
    print(f"  [created] webhook {wh.id} -> {url}")
    print(f"  *** ADD TO .env: STRIPE_WEBHOOK_SECRET={wh.secret} ***")
    return wh


def setup_portal() -> stripe.billing_portal.Configuration:
    configs = stripe.billing_portal.Configuration.list(active=True).data
    if configs:
        print(f"  [exists] portal config {configs[0].id}")
        return configs[0]
    cfg = stripe.billing_portal.Configuration.create(
        business_profile={
            "headline": "Gérez votre abonnement KT Monetization OS",
            "privacy_policy_url": f"https://{DOMAIN}/privacy",
            "terms_of_service_url": f"https://{DOMAIN}/terms",
        },
        features={
            "subscription_cancel": {"enabled": True, "mode": "at_period_end"},
            "payment_method_update": {"enabled": True},
            "invoice_history": {"enabled": True},
        },
    )
    print(f"  [created] portal config {cfg.id}")
    return cfg


def main():
    print("\n[1/3] Products & Prices")
    results = {}
    for plan in PLANS:
        results[plan["key"]] = upsert_product_and_price(plan)

    print("\n[2/3] Webhook")
    wh = setup_webhook()

    print("\n[3/3] Customer Portal")
    setup_portal()

    # Save IDs
    os.makedirs("stripe", exist_ok=True)
    output = {
        "mode": MODE,
        "domain": DOMAIN,
        "generated_at": datetime.utcnow().isoformat(),
        "products": results,
        "webhook_id": wh.id,
    }
    with open("stripe/stripe_ids.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\n✅ stripe/stripe_ids.json saved")
    print("\n--- COPY TO .env ---")
    if results.get("pro", {}).get("price_id", "free") != "free":
        print(f"STRIPE_PRICE_PRO_MONTHLY_ID={results['pro']['price_id']}")
    if results.get("business", {}).get("price_id", "free") != "free":
        print(f"STRIPE_PRICE_BUSINESS_MONTHLY_ID={results['business']['price_id']}")
    print("--------------------")


if __name__ == "__main__":
    main()
