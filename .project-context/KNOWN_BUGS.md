# KNOWN BUGS — KT Monetization OS
## Mis à jour : 2026-04-02

---

## 🔴 CRITIQUE

### BUG-001 — @stripe/react-stripe-js absent du frontend
- **Symptôme :** Impossible d'intégrer Stripe.js côté front (bouton checkout muet)
- **Fichier :** `frontend/client/package.json`
- **Fix :** `npm install @stripe/react-stripe-js @stripe/stripe-js`
- **Statut :** ❌ Non corrigé

### BUG-002 — STRIPE_PRICE_PRO_YEARLY_ID vide
- **Symptôme :** Un checkout avec `interval=yearly` lèvera une erreur Stripe (price_id vide)
- **Fichier :** `.env`
- **Fix :** Créer les prix yearly dans Stripe et remplir les variables
- **Statut :** ❌ Non corrigé

### BUG-003 — Credit ledger incomplet
- **Symptôme :** POST `/api/v1/billing/credits/purchase` crée une session Stripe mais ne met pas à jour les crédits user en DB après paiement
- **Fichiers :** `backend/api/models/user.py` (pas de champ `credits`), `backend/api/services/billing_service.py`
- **Fix :** Ajouter champ `credits` au modèle User + handler dans `handle_checkout_completed` pour mode `credit_pack`
- **Statut :** ❌ Non corrigé

---

## 🟡 IMPORTANT

### BUG-004 — RESEND_API_KEY absent
- **Symptôme :** Emails de bienvenue, confirmation billing et alerte paiement échoué sont silencieux (loggués seulement)
- **Fichier :** `.env`
- **Fix :** Ajouter `RESEND_API_KEY=re_xxx` (créer compte sur resend.com)
- **Statut :** ❌ Non corrigé

### BUG-005 — API non démarrée, PostgreSQL non actif
- **Symptôme :** `http://localhost:8010/health` → timeout
- **Cause probable :** Pas de serveur PostgreSQL local actif (DATABASE_URL pointe vers localhost:5432)
- **Fix :** Lancer PostgreSQL local OU basculer DATABASE_URL sur SQLite en dev :
  `DATABASE_URL=sqlite+aiosqlite:///./dev.db`
- **Statut :** ❌ À vérifier

### BUG-006 — Webhook n'alimente pas audit_logs
- **Symptôme :** Les changements d'abonnement (subscription.updated, invoice.payment_failed) ne sont pas tracés dans `audit_logs`
- **Fichier :** `backend/api/services/billing_service.py` (handlers webhook)
- **Fix :** Ajouter un insert dans `audit_logs` dans les handlers Stripe
- **Statut :** ❌ Non corrigé

### BUG-007 — TODO dans mobile.py (métriques factices)
- **Symptôme :** L'endpoint de métriques mobile retourne des données placeholder
- **Fichier :** `backend/api/routers/mobile.py` ligne 344
  ```python
  # TODO: replace with real metrics from DB once analytics module is built
  ```
- **Fix :** Implémenter requête réelle sur UsageRecord + events
- **Statut :** ❌ Non corrigé (non bloquant)

---

## 🟢 MINEUR / INFORMATIF

### INFO-001 — Deux dépôts locaux confusants
- `C:\Users\Alienware\TKVerse\` → monorepo original (référence)
- `C:\Users\Alienware\kt-monetization-os\` → **repo actif**
- `C:\Users\Alienware\kt-monetization-os-needed-copy-20260327-112659\` → backup identique (ignorer)
- **Action :** Toujours travailler dans `kt-monetization-os/`

### INFO-002 — Stripe en mode TEST
- Toutes les clés commencent par `sk_test_` / `pk_test_`
- Ne jamais passer en production sans changer vers `sk_live_`
- Le webhook ID `we_1TErAkARjyNV3UuRpvIUf85b` est TEST

### INFO-003 — Python 3.14 (version très récente)
- Système utilise Python 3.14.3 (beta/rc)
- Certains packages pourraient ne pas supporter 3.14
- Si des erreurs d'installation apparaissent : utiliser `pyenv` pour installer Python 3.12
- Le `.venv` dans le dossier est potentiellement pour Python 3.14

### INFO-004 — DATABASE_URL vers PostgreSQL local
- `.env` pointe vers `localhost:5432`
- PostgreSQL n'est probablement pas actif localement
- Pour dev rapide : utiliser SQLite → `DATABASE_URL=sqlite+aiosqlite:///./dev.db`
- L'API utilise `Base.metadata.create_all` au démarrage → tables créées automatiquement
