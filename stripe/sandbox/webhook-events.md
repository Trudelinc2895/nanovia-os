# Stripe sandbox webhooks

Support these Stripe test-mode events:

- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`
- `customer.subscription.trial_will_end`

Inject the resulting webhook secret into `.env.sandbox` as `STRIPE_WEBHOOK_SECRET`.
