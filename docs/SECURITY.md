# Security Sandbox

## Garde-fous actifs

- `STRIPE_MODE=test` obligatoire en sandbox
- clés `sk_live_*` et `pk_live_*` refusées si `SANDBOX_ALLOW_LIVE_KEYS=false`
- secret webhook live détectable refusé en sandbox
- actions dangereuses bloquées par défaut
- mémoire sandbox refuse les contenus qui ressemblent à des secrets
- `docker-compose.sandbox.yml` doit rester en `APP_ENV=sandbox`

## Audit

Fichier principal:

`data\audit\sandbox-audit.jsonl`

Chaque entrée contient:

- `timestamp`
- `environment`
- `actor`
- `agent`
- `action`
- `target`
- `status`
- `risk_level`
- `details`
