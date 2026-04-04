# RUNBOOK — KT Monetization OS

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
# Si .env existe déjà, vérifier les variables critiques :
# DATABASE_URL, JWT_SECRET_KEY, STRIPE_SECRET_KEY
# Pour dev SQLite rapide, remplacer DATABASE_URL :
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
# Vérifier .env.local :
# NEXT_PUBLIC_API_URL=http://localhost:8010
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
# Dev :
docker-compose -f infra/docker-compose.prod.yml up -d

# Vérifier :
docker-compose ps
```

---

## 6. Check Santé Rapide

```powershell
# API backend
Invoke-WebRequest -Uri "http://localhost:8010/health" -ErrorAction SilentlyContinue | Select-Object StatusCode, Content

# API ready (check DB + Redis)
Invoke-WebRequest -Uri "http://localhost:8010/ready" -ErrorAction SilentlyContinue | Select-Object StatusCode, Content

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
STRIPE_PRICE_PRO_MONTHLY_ID   → price_1TErAj...
STRIPE_PRICE_BUSINESS_MONTHLY_ID → price_1TErAj...
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
```
