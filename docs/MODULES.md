# Modules Sandbox

Le catalogue officiel sandbox vit dans `shared\catalog\monetization.json` sous `official_sandbox`.

## Modules officiels

1. `core_platform`
2. `billing_monetization`
3. `ai_orchestrator`
4. `memory_system`
5. `super_admin`
6. `devops_control`
7. `security_center`
8. `automation_bots`
9. `support_crm`
10. `analytics_monitoring`
11. `notification_center`
12. `integration_hub`

Chaque module expose:

- `id`
- `name`
- `description`
- `category`
- `enabled`
- `required_plan`
- `permissions`
- `routes`
- `agent_support`
- `billing_metered`
- `sandbox_enabled`
- `production_ready`

## Admin sandbox

- `GET /admin/modules`
- `POST /admin/modules/{id}/toggle-sandbox`

L'API reste la source de vérité pour l'activation réelle.
