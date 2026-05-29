# Stripe Sandbox

## Fichiers

- `stripe\sandbox\products.json`
- `stripe\sandbox\prices.json`
- `stripe\sandbox\setup-stripe-sandbox.ps1`
- `stripe\sandbox\stripe-output.sandbox.json`
- `stripe\stripe_ids.json`

## Bootstrap

```powershell
cd C:\Users\Alienware\nanovia-os
powershell -ExecutionPolicy Bypass -File .\stripe\sandbox\setup-stripe-sandbox.ps1
```

## Événements webhook couverts

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`
- `customer.subscription.trial_will_end`
- `customer.updated`
- `payment_method.attached`

## Stripe CLI

```powershell
stripe login
stripe listen --forward-to localhost:8000/stripe/webhook
```
