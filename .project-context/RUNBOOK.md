# RUNBOOK — Nanovia OS

## Prérequis Locaux

- Python 3.12+ (3.14 confirmé présent)
- Node.js 18+
- PostgreSQL 16 OU SQLite (dev)
- Redis (ou skip si indisponible — fail open)
- Stripe CLI (optionnel, pour tester les webhooks)

---

## 1. Setup Backend (FastAPI)

### Installer les dépendances
```powershell
cd C:\Users\Alienware\kt-monetization-os
pip install -r backend/requirements.txt
```

### Configurer l'env
```powershell
# Copier le template racine si nécessaire :
# Copy-Item .env.example .env
#
# Vérifier surtout :
# APP_ENV, DATABASE_URL, JWT_SECRET_KEY, STRIPE_SECRET_KEY,
# PUBLIC_WEB_URL, PRIVATE_ADMIN_URL, ADMIN_ALLOWED_IPS
# Pour dev SQLite rapide :
# DATABASE_URL=sqlite+aiosqlite:///./dev.db
```

### Lancer l'API (dev)
```powershell
cd C:\Users\Alienware\kt-monetization-os
$env:PYTHONPATH = "backend"
uvicorn api.main:app --reload --host 127.0.0.1 --port 8010
```

### Vérifier /health
```powershell
Invoke-WebRequest -Uri "http://localhost:8010/health" | Select-Object -ExpandProperty Content
# Attendu: {"status":"ok",...}
```

### Vérifier /docs (Swagger)
Ouvrir dans un navigateur : http://localhost:8010/docs

---

## 2. Setup Frontend (Next.js Web)

### Installer les dépendances
```powershell
cd C:\Users\Alienware\kt-monetization-os\frontend\client
npm install
```

### Configurer l'env frontend
```powershell
# Créer frontend\client\.env.local si nécessaire :
# NEXT_PUBLIC_API_URL=http://127.0.0.1:8010
# NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED=false
```

### Lancer le frontend
```powershell
npm run dev
# Ouvre : http://localhost:3000
```

### Build de production
```powershell
npm run build
npm run start
```

---

## 3. Setup Stripe (local webhook forwarding)

### Installer Stripe CLI
```powershell
# Windows : https://stripe.com/docs/stripe-cli
# Ou via scoop : scoop install stripe
```

### Écouter les webhooks en local
```powershell
stripe listen --forward-to localhost:8010/api/v1/billing/webhook
# Copier le "webhook signing secret" (whsec_...) dans .env → STRIPE_WEBHOOK_SECRET
```

### Tester un paiement test
```powershell
stripe trigger checkout.session.completed
```

---

## 4. Bootstrap Stripe (créer produits/prix — 1 fois)

```powershell
cd C:\Users\Alienware\kt-monetization-os
python stripe/setup_stripe.py
# → Génère stripe/stripe_ids.json avec les IDs
# → Copier les price_ids dans .env
```

---

## 5. Démarrage Complet (Docker — prod)

```powershell
cd C:\Users\Alienware\kt-monetization-os

# Production public stack
Copy-Item infra\env\.env.example .env.production
python scripts\validate_runtime_env.py --env-file .env.production --target-env production
docker compose -p nanovia-prod -f infra\docker-compose.prod.yml --env-file .env.production up -d

# Staging isolé sur le même VPS (ports loopback + pas de Caddy)
Copy-Item infra\env\.env.staging.example .env.staging
python scripts\validate_runtime_env.py --env-file .env.staging --target-env staging
docker compose -p nanovia-staging -f infra\docker-compose.prod.yml -f infra\docker-compose.staging.yml --env-file .env.staging up -d

# Vérifier :
docker compose ps
```

### Déploiement GitHub Actions (OVH)

- `main` => environnement GitHub `production`
- `staging` => environnement GitHub `staging`
- `APP_RUNTIME_ENV_FILE` doit pointer vers le bon fichier (`../.env.production`, `../.env.staging` ou `../.env` legacy)
- Le préflight `scripts\validate_runtime_env.py` bloque maintenant les placeholders restants, l'absence de `TOTP_ENCRYPTION_KEY` et l'oubli de l'allowlist admin en production.
- Secrets attendus par environnement :
  - `VPS_HOST`
  - `VPS_SSH_PRIVATE_KEY`
  - `DEPLOY_PATH`
- Variables utiles :
  - `APP_DOMAIN`, `PUBLIC_IP`
  - `STAGING_BIND_ADDRESS`, `STAGING_WEB_PORT`, `STAGING_ADMIN_PORT`, `STAGING_API_PORT`, `STAGING_AI_PORT`
- Garde-fous actuels du workflow :
  - `production` exige `STRIPE_SECRET_KEY=sk_live_...`
  - `staging` refuse les clés Stripe live
  - `APP_RUNTIME_ENV_FILE` est réécrit vers `../.env.production` ou `../.env.staging`

### Accès staging recommandé

```powershell
ssh -L 13000:127.0.0.1:13000 -L 13020:127.0.0.1:13020 -L 18010:127.0.0.1:18010 deploy@VPS_HOST
```

- Web staging : `http://127.0.0.1:13000`
- Admin staging : `http://127.0.0.1:13020`
- API staging : `http://127.0.0.1:18010`
- Garder Stripe en `sk_test_...` / `pk_test_...` / `whsec_...`
- En production, le frontend admin reste un service séparé mais n'est pas publié publiquement par le `Caddyfile` par défaut.

---

## 6. Check Santé Rapide

```powershell
# API backend
Invoke-WebRequest -Uri "http://localhost:8010/health" -ErrorAction SilentlyContinue | Select-Object StatusCode, Content

# API ready (check DB + Redis)
Invoke-WebRequest -Uri "http://localhost:8010/api/v1/health/ready" -ErrorAction SilentlyContinue | Select-Object StatusCode, Content

# Frontend
Invoke-WebRequest -Uri "http://localhost:3000" -ErrorAction SilentlyContinue | Select-Object StatusCode

# Script de vérification intégré
python scripts/check_health.py
```

---

## 7. Variables d'Env Critiques à Vérifier

```
DATABASE_URL          → doit pointer vers postgres (prod) ou sqlite (dev)
JWT_SECRET_KEY        → doit être long et aléatoire
STRIPE_SECRET_KEY     → sk_test_... (dev) ou sk_live_... (prod)
STRIPE_WEBHOOK_SECRET → whsec_... (obtenu via stripe listen ou dashboard)
PUBLIC_WEB_URL        → URL publique utilisée pour Stripe/email
PRIVATE_ADMIN_URL     → URL/admin origin privé
APP_RUNTIME_ENV_FILE  → ../.env.production ou ../.env.staging en Docker
ADMIN_ALLOWED_IPS     → CIDR(s) autorisés pour /api/v1/admin/*
PRIVATE_ORCHESTRATOR_ENABLED      → true uniquement si le slice admin privé doit répondre
NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED → true uniquement pour afficher l'UI admin
STRIPE_PRICE_PRO_MONTHLY_ID   → price_1TErAj...
STRIPE_PRICE_PRO_YEARLY_ID    → price_...
STRIPE_PRICE_BUSINESS_MONTHLY_ID → price_1TErAj...
STRIPE_PRICE_BUSINESS_YEARLY_ID  → price_...
```

---

## 8. Commandes Utiles

```powershell
# Voir les logs API (si démarré en arrière-plan)
Get-Content logs\api.log -Tail 50
Get-Content logs\api_err.log -Tail 20

# Tester la config Python
cd C:\Users\Alienware\kt-monetization-os
python -c "import sys; sys.path.insert(0,'backend'); from api.config import settings; print(settings.APP_NAME)"

# Vérifier les routes disponibles
python -c "import sys; sys.path.insert(0,'backend'); from api.main import app; [print(r.path) for r in app.routes]"

# Lister les derniers webhooks Stripe (admin token requis)
curl.exe -H "Authorization: Bearer ADMIN_TOKEN" http://127.0.0.1:8010/api/v1/admin/webhooks

# Rejouer un webhook stocké (forcer si déjà processed)
curl.exe -X POST -H "Authorization: Bearer ADMIN_TOKEN" -H "Content-Type: application/json" `
  -d "{\"force\":true}" http://127.0.0.1:8010/api/v1/admin/webhooks/EVENT_ID/reprocess

# Resynchroniser l'abonnement d'un utilisateur depuis Stripe
curl.exe -X POST -H "Authorization: Bearer ADMIN_TOKEN" `
  http://127.0.0.1:8010/api/v1/admin/users/USER_ID/resync-subscription

# Vérifier le slice private orchestrator (404 si flag off)
curl.exe -H "Authorization: Bearer ADMIN_TOKEN" http://127.0.0.1:8010/api/v1/admin/orchestrator/overview
```

### Notes opérateur

- Le slice private orchestrator reste **admin-only**, **feature-flagged** et **read-only**.
- Flags requis pour le rendre visible :
  - API : `PRIVATE_ORCHESTRATOR_ENABLED=true`
  - Frontend admin : `NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED=true`
- Endpoints publiés :
  - `/api/v1/admin/orchestrator/overview`
  - `/api/v1/admin/orchestrator/agents`
- Recovery Stripe :
  - d'abord inspecter `/api/v1/admin/webhooks`
  - ensuite `reprocess`
  - si l'état utilisateur reste incohérent, lancer `resync-subscription`
