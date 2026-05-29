# Stripe sandbox webhook test events

Événements à valider dans le backend sandbox:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`
- `customer.subscription.trial_will_end`
- `customer.updated`
- `payment_method.attached`

Le handler sandbox doit vérifier la signature, rester idempotent, auditer l'événement, puis recalculer les entitlements.
