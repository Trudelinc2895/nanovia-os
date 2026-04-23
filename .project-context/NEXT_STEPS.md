# NEXT STEPS — Nanovia OS
## Mis à jour : 2026-04-02

Les étapes sont ordonnées par impact/urgence. Attaquer une à la fois.

---

## 🔴 ÉTAPE 1 — Vérifier que l'API démarre (5 min)

**Pourquoi :** Rien ne peut être testé sans que l'API tourne.

```powershell
cd C:\Users\Alienware\kt-monetization-os
$env:PYTHONPATH = "backend"
# Option A : PostgreSQL disponible → lancer tel quel
uvicorn api.main:app --reload --host 127.0.0.1 --port 8010

# Option B : Pas de PostgreSQL → basculer en SQLite pour dev
# Dans .env, remplacer DATABASE_URL par :
# DATABASE_URL=sqlite+aiosqlite:///./dev.db
```

**Fichiers touchés :** `.env` uniquement (si SQLite)
**Vérification :** `Invoke-WebRequest http://localhost:8010/health`

---

## 🔴 ÉTAPE 2 — Ajouter @stripe/react-stripe-js au frontend (5 min)

**Pourquoi :** Le bouton "Upgrade" du frontend ne peut pas initier un checkout sans cette lib.

```powershell
cd C:\Users\Alienware\kt-monetization-os\frontend\client
npm install @stripe/react-stripe-js @stripe/stripe-js
```

**Fichiers touchés :** `frontend/client/package.json`, `package-lock.json`

---

## 🔴 ÉTAPE 3 — Configurer les yearly price IDs Stripe (10 min)

**Pourquoi :** Si affichés dans le front, les yearly checkouts échouent.

```powershell
# Option A : Créer les prix yearly via setup_stripe.py (modifier le script)
# Option B : Créer manuellement dans le Stripe Dashboard (TEST)
# → Copier les price_id générés dans .env :
# STRIPE_PRICE_PRO_YEARLY_ID=price_xxx
# STRIPE_PRICE_BUSINESS_YEARLY_ID=price_xxx
```

**Fichiers touchés :** `.env`, `stripe/setup_stripe.py` (si modifié)

---

## 🟡 ÉTAPE 4 — Implémenter le credit ledger (1h)

**Pourquoi :** L'endpoint `/billing/credits/purchase` existe mais les crédits ne s'ajoutent pas.

Actions :
1. Ajouter champ `credits` (int, default=0) au modèle `User` dans `backend/api/models/user.py`
2. Ajouter logique d'incrémentation dans `billing_service.py` après `checkout.session.completed` (mode `credit_pack`)
3. Vérifier que `STRIPE_CREDIT_PRICE_ID` est configuré dans `.env`

**Fichiers touchés :**
- `backend/api/models/user.py`
- `backend/api/services/billing_service.py`
- `.env`

---

## 🟡 ÉTAPE 5 — Tester le flow Stripe end-to-end (30 min)

```powershell
# Terminal 1 : API
uvicorn api.main:app --reload --port 8010

# Terminal 2 : Stripe webhook listener
stripe listen --forward-to localhost:8010/api/v1/billing/webhook

# Terminal 3 : Déclencher un checkout test
stripe trigger checkout.session.completed
```

**À vérifier :**
- User.plan mis à jour après checkout
- Email de confirmation envoyé (ou loggué)
- `GET /api/v1/billing/entitlements` retourne le bon plan

---

## 🟡 ÉTAPE 6 — Configurer RESEND_API_KEY (10 min)

**Pourquoi :** Les emails sont silencieux (loggués seulement) sans cette clé.

```
1. Créer un compte sur resend.com (gratuit)
2. Générer une API key
3. Ajouter dans .env : RESEND_API_KEY=re_xxx
```

**Fichiers touchés :** `.env` uniquement

---

## 🟢 ÉTAPE 7 — Générer les migrations Alembic (20 min)

**Pourquoi :** Les tables sont créées via `Base.metadata.create_all` au démarrage (dev) mais Alembic est nécessaire pour la prod.

```powershell
cd C:\Users\Alienware\kt-monetization-os\backend
alembic init migrations  # si pas encore fait
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

---

## 🟢 ÉTAPE 8 — Déployer en prod (VPS)

```powershell
# 1. Remplacer stripe_test_ par stripe_live_ dans .env
# 2. Changer APP_ENV=production
# 3. Lancer bootstrap VPS
bash scripts/bootstrap_vps.sh
```

---

## Pour chaque nouvelle session

1. Lire `WORKSTATE.md` → identifier ce qui est fait/cassé
2. Lire `KNOWN_BUGS.md` → éviter de retomber sur les mêmes erreurs
3. Choisir la prochaine étape dans ce fichier (la plus haute non cochée)
4. Après chaque étape : mettre à jour `WORKSTATE.md` + `KNOWN_BUGS.md`
