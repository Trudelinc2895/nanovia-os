# Nanovia Sandbox

Le sandbox Nanovia est une **couche intégrée** au repo existant pour tester Stripe, les modules, les entitlements, les agents, les bots, la mémoire, l'admin, la sécurité et les garde-fous de rentabilité **sans toucher au live**.

## Ce qui est branché

- `GET /sandbox/status` : état global, garde-fous et rentabilité estimée
- `GET /modules`, `GET /billing/plans`, `GET /billing/entitlements`
- `POST /billing/checkout`, `POST /billing/portal`, `POST /stripe/webhook`
- `GET /credits`, `GET /usage`, `POST /usage/record`
- `GET /agents`, `POST /agents/route`, `GET /bots`, `POST /bots/{id}/run`
- `GET /admin/workspaces`, `POST /admin/workspaces/{id}/override-plan`
- `POST /admin/workspaces/{id}/block`, `/unblock`, `/credits/adjust`

## Démarrage

```powershell
cd C:\Users\Alienware\nanovia-os
copy .env.sandbox.example .env.sandbox
docker compose -f docker-compose.sandbox.yml up -d --build
```

## Vérifications rapides

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/modules
curl http://localhost:8000/billing/plans
curl "http://localhost:8000/billing/entitlements?workspace_id=sandbox_pro"
curl http://localhost:8000/sandbox/status
```

## Garde-fous

- `APP_ENV=sandbox` obligatoire pour les routes sandbox
- clés Stripe live refusées si `SANDBOX_ALLOW_LIVE_KEYS=false`
- actions dangereuses bloquées sans confirmation
- workspace bloqué => usage, agents, bots et checkout refusés
- mémoire sandbox refuse le contenu ressemblant à un secret

## Rentabilité OpenAI

Les plans sandbox embarquent un budget AI et une cible de marge:

- Starter : budget OpenAI de 6 USD / mois
- Pro : budget OpenAI de 18 USD / mois
- Business : budget OpenAI de 45 USD / mois

Le sandbox suit les crédits consommés, estime le coût OpenAI par usage, et remonte la marge estimée dans `/billing/entitlements` et `/sandbox/status`.
