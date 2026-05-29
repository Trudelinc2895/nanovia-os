# Billing Sandbox

La logique sandbox suit cette formule comme source de vérité:

`workspace + plan + subscription_status + credits + usage + admin_overrides = entitlements`

## Plans officiels

| Plan | Prix | Modules clés | Budget AI |
| --- | ---: | --- | ---: |
| Starter | 29 USD/mois | core_platform, billing_monetization, support_crm | 6 USD |
| Pro | 79 USD/mois | Starter + ai_orchestrator, memory_system, analytics_monitoring | 18 USD |
| Business | 149 USD/mois | Pro + devops_control, security_center, automation_bots, super_admin, notification_center, integration_hub | 45 USD |

## Endpoints

- `GET /billing/plans`
- `GET /billing/entitlements`
- `GET /billing/subscription`
- `POST /billing/checkout`
- `POST /billing/portal`
- `POST /stripe/webhook`
- `GET /credits`
- `GET /usage`
- `POST /usage/record`

## Règles

- l'API décide toujours l'accès
- les crédits sont traçables via ledger + events
- les workspaces `past_due`, `unpaid`, `canceled` ou `blocked` perdent l'accès premium
- les ajustements admin exigent une raison
- le sandbox suit la marge estimée OpenAI
