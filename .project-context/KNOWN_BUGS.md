# KNOWN BUGS — Nanovia OS
## Mis à jour : 2026-04-27

---

## 🔴 BLOQUANTS DE CONFIGURATION

### BUG-001 — Catalogue Stripe incomplet tant que les price IDs ne sont pas injectés
- **Symptôme :** Les checkouts Pro/Business ou add-ons échouent si les variables `STRIPE_PRICE_*` restent vides ou placeholder.
- **Fichiers :** `.env.dev`, `.env.production`, `.env.staging`
- **Fix :** Exécuter `python stripe/setup_stripe.py` avec des clés Stripe valides puis copier les IDs générés dans le fichier d'environnement ciblé.
- **Statut :** ⏳ En attente de vraies valeurs Stripe

### BUG-002 — Intégrations email inactives sans `RESEND_API_KEY`
- **Symptôme :** Les emails transactionnels restent loggués sans partir réellement.
- **Fichiers :** `.env.dev`, `.env.production`, `.env.staging`
- **Fix :** Fournir une clé Resend valide.
- **Statut :** ⏳ En attente de vraie clé Resend

---

## 🟡 IMPORTANT

### BUG-003 — `mobile.py` expose encore des métriques placeholder
- **Symptôme :** L'endpoint de métriques mobile retourne des données placeholder
- **Fichier :** `backend/api/routers/mobile.py` ligne 344
  ```python
  # TODO: replace with real metrics from DB once analytics module is built
  ```
- **Fix :** Implémenter requête réelle sur UsageRecord + events
- **Statut :** ⏳ Non corrigé (non bloquant)

---

## 🟢 DÉJÀ CORRIGÉ / VÉRIFIÉ

### FIX-001 — Dépendances Stripe frontend présentes
- `frontend/client/package.json` inclut déjà `@stripe/react-stripe-js` et `@stripe/stripe-js`
- Le build frontend passe

### FIX-002 — Credit ledger déjà branché
- `backend/api/models/user.py` contient `credits`
- `backend/api/services/credit_service.py` centralise le ledger
- `billing_service.py` ajoute les crédits sur `checkout.session.completed`

### FIX-003 — Audit billing présent côté webhook
- `billing_service.py` écrit déjà dans `audit_logs` pour les événements critiques
- Le problème documenté auparavant était obsolète

### FIX-004 — Démarrage local simplifié
- Un `infra/docker-compose.dev.yml` existe maintenant pour démarrer web + api + postgres + redis
- Le fallback SQLite reste documenté pour les cas sans Docker

### FIX-005 — Socle dev unifié
- Référence officielle : **Python 3.12 + Node 20**
- README et CI alignés sur cette base

## ℹ️ CONTEXTE

- `C:\Users\Alienware\nanovia-os\` → repo actif
- `C:\Users\Alienware\nanovia-os-needed-copy-20260327-112659\` → backup local à ignorer

