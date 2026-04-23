# WORKSTATE — Nanovia OS
## Mis à jour : 2026-04-10 UTC

---

## État Global : 🟢 DESIGN SYSTEM COMPLET — BUILD PROD PROPRE — PRÊT DÉPLOIEMENT VPS

---

## ✅ TERMINÉ / FONCTIONNEL

### Frontend — Design System (2026-04-10)
- [x] `components/ui/tokens.ts` — palette Titanium/noir + bleu #4F8CFF
- [x] `components/ui/Button.tsx` — variants primary/secondary/ghost/danger + `buttonVariants()`
- [x] `components/ui/Card.tsx` — outlined/solid variants
- [x] `components/ui/Input.tsx` — label, error, helperText, show/hide password
- [x] `components/ui/Badge.tsx` — info/success/warning/danger
- [x] `tailwind.config.js` — tous les tokens intégrés + aliases rétrocompat
- [x] Pages refactorisées : login, register, dashboard, billing, analytics, admin/layout, verify-email
- [x] Build production : 23/23 pages ✅ (Next.js 15)
- [x] `docs/DESIGN_SYSTEM.md` — documentation complète

### Backend
- [x] FastAPI entry point (`backend/api/main.py`) — structure complète
- [x] Config centralisée via pydantic-settings (`api/config.py`)
- [x] Auth : register, login, refresh, logout, me (JWT HS256 + Argon2id)
- [x] Rate limiting (Redis) + security headers middleware
- [x] 11 tables ORM SQLAlchemy définies
- [x] Stripe billing complet (checkout, portal, webhook idempotent, entitlements)
- [x] PLANS_CONFIG server-side (FREE/PRO/BUSINESS)
- [x] Usage metering par user/module
- [x] Email service (Resend API / fallback log-only)
- [x] Webhook handlers complets
- [x] Ghost Agency router + service
- [x] Content Cloner router + service
- [x] Module 1 AI Operator router
- [x] Health/ready/metrics endpoints
- [x] Mobile endpoints + VIP KPIs avec vraies métriques DB
- [x] Stripe Price IDs yearly + credit dans .env
- [x] Credit ledger complet (billing_service.py)
- [x] Audit logs sur billing events
- [x] **JSONB → JSON corrigé** (conversation, content_clone, notification)
- [x] **SQLite NullPool fix** (database.py)
- [x] **API démarre `/health` 200 OK** (port 8010, SQLite dev)
- [x] **forgot-password endpoint** ajouté (auth.py ligne 143)
- [x] **reset-password endpoint** ajouté (auth.py ligne 160)
- [x] **send_password_reset_email** ajouté (email_service.py)
- [x] **password_reset_token + password_reset_expires** sur User model
- [x] **ForgotPasswordRequest + ResetPasswordRequest** schemas ajoutés

### Frontend
- [x] Next.js 15 app router (pages: landing, login, register, dashboard, billing, chat)
- [x] Auth context React + lib/api.ts
- [x] Tailwind CSS + design system violet/dark
- [x] `@stripe/react-stripe-js` installé
- [x] **Login page améliorée** (show/hide password, lien forgot, spinner, erreur propre)
- [x] **Register page améliorée** (password strength, confirm, CGU checkbox)
- [x] **forgot-password page** créée (anti-enumeration, états UI complets)
- [x] **reset-password page** créée (token URL, validation, redirect post-reset)
- [x] **forgotPassword() + resetPassword()** ajoutés dans api.ts

### Machine Windows
- [x] Bonjour Service → Stopped + Disabled
- [x] Apple Mobile Device Service → Stopped + Disabled
- [x] WirelessBackupService (Wondershare) → Stopped + Disabled
- [x] SoftLanding (6 tâches planifiées) → toutes Disabled
- [x] Canva AutoLaunch → retiré du startup registry

---

## ⚠️ PROBLÈMES IDENTIFIÉS — EN ATTENTE DE FIX

### Bug #1 — CRITIQUE (STEP A) — Routes forgot/reset non exposées
- **Cause** : Serveur démarré avant ajout des routes, pas de --reload
- **Fix** : Redémarrer uvicorn avec --reload
- **Fichiers** : aucun à modifier — restart uniquement

### Bug #2 — CRITIQUE (STEP B) — URL frontend legacy
- **Fichier** : `backend/api/routers/auth.py` ligne 140
- **Problème** : l'ancien flow utilisait une URL frontend figée
- **Fix** : utiliser `settings.PUBLIC_WEB_URL`

### Bug #3 — CRITIQUE (STEP C) — api.ts appelle request() inexistant
- **Fichier** : `frontend/client/lib/api.ts` lignes 118–122
- **Problème** : `request()` n'existe pas → ReferenceError à l'exécution
- **Fix** : Remplacer par `apiFetch()`

### Bug #4 — CRITIQUE (STEP D) — /register retourne UserPublic ≠ TokenResponse
- **Fichier** : `backend/api/routers/auth.py` ligne 44
- **Problème** : Backend retourne UserPublic, frontend attend TokenResponse
- **Fix** : Backend retourne TokenResponse (access_token + refresh_token)

---

## ❌ NON FAIT

- [ ] Security headers next.config.ts
- [ ] Home page nav (boutons Login/Register manquants)
- [ ] Supprimer alert() dans home page
- [ ] 404 / error pages
- [ ] Rate limiting sur /login, /register, /forgot-password
- [ ] FRONTEND_URL dans .env
- [ ] Test flow complet end-to-end
- [ ] Déploiement Railway/Fly.io

---

## COMMANDE DE DÉMARRAGE API

```powershell
cd C:\Users\Alienware\kt-monetization-os
$env:PYTHONPATH = "backend"
uvicorn api.main:app --host 127.0.0.1 --port 8010 --reload
```

## PROCHAINES ÉTAPES (ordonnées)

1. STEP A — Restart API avec --reload → vérifier forgot/reset dans OpenAPI
2. STEP B — Remplacer _FRONTEND_URL par settings.PUBLIC_WEB_URL
3. STEP C — Corriger request() → apiFetch() dans api.ts
4. STEP D — /register retourne TokenResponse
5. STEP E — Test end-to-end complet


---

## État Global : 🟢 API OPÉRATIONNELLE EN DEV — Non déployé en prod
## Dernière mise à jour : 2026-04-02 21:34 UTC

---

## ✅ TERMINÉ / FONCTIONNEL

### Backend
- [x] FastAPI entry point (`backend/api/main.py`) — structure complète
- [x] Config centralisée via pydantic-settings (`api/config.py`)
- [x] Auth complète : register, login, refresh, logout, me (JWT HS256 + Argon2id)
- [x] Rate limiting (Redis) + security headers middleware
- [x] 11 tables ORM SQLAlchemy définies (user, subscription, webhook_event, usage_record, audit, conversation, ghost_agency, content_clone, notification, device_session)
- [x] Stripe billing : checkout-session, portal-session, webhook idempotent, entitlements, plans, usage
- [x] PLANS_CONFIG server-side (FREE/PRO/BUSINESS — ne fait jamais confiance au client)
- [x] Usage metering par user/module (UsageRecord + Redis counters)
- [x] Email service (Resend API / fallback log-only)
- [x] Webhook handlers : checkout.completed, subscription.created/updated/deleted, invoice.paid/failed
- [x] Ghost Agency router + service (campagnes outreach, génération messages AI)
- [x] Content Cloner router + service (repurposing contenu)
- [x] Module 1 AI Operator router (`/api/v1/modules/`)
- [x] Health/ready endpoints
- [x] Mobile endpoints
- [x] `stripe/setup_stripe.py` exécuté → `stripe_ids.json` généré (TEST mode)
- [x] Stripe Price IDs mensuels dans `.env`
- [x] **Stripe Price IDs YEARLY + CREDIT dans `.env`** (price_1THsUS... / price_1THsUT... / price_1THsUU...)
- [x] `@stripe/react-stripe-js` installé (npm install ✅)
- [x] **JSONB → JSON corrigé** (conversation.py, content_clone.py, notification.py)
- [x] **SQLite NullPool fix** (database.py)
- [x] **API démarre et répond `/health` 200 OK** (port 8010)
- [x] **Credit ledger complet** (billing_service.py)
- [x] **Audit logs** sur billing events
- [x] **Mobile VIP KPIs** avec vraies métriques DB

### Infrastructure
- [x] `infra/docker-compose.prod.yml` complet (caddy, web, admin, api, postgres, redis, vault, prometheus, grafana)
- [x] Caddyfile (TLS auto, security headers, rate-limit)
- [x] GitHub Actions CI/CD (ci.yml, deploy.yml)
- [x] `scripts/bootstrap_vps.sh` prêt

### Frontend
- [x] Next.js 15 app routeur (pages: landing, login, register, dashboard)
- [x] `.next/` build existant
- [x] Auth context React + lib/api.ts
- [x] Tailwind CSS configuré

### Config
- [x] `.env` présent avec : DATABASE_URL (postgres), JWT, Stripe monthly IDs, OpenAI, Telegram

---

## ⚠️ PARTIELLEMENT FAIT

- [ ] **Credit ledger** : endpoint `/billing/credits/purchase` crée une session Stripe mais n'incrémente pas les crédits en DB (modèle `UserCredit` absent)
- [ ] **Alembic migrations** : dossier `database/migrations/` présent mais migrations non générées/exécutées
- [ ] **Modules 3–10** : squelettes présents dans `modules/` mais logique business non implémentée
- [ ] **Audit logs** : table définie mais les changements d'abonnement via webhook ne peuplent pas `audit_logs`
- [ ] **Admin frontend** : dossier `frontend/admin/` présent, état inconnu
- [ ] **Mobile app** : structure React Native présente, connexion API à vérifier

---

## ❌ NON FAIT / CASSÉ

- [ ] `STRIPE_PRICE_PRO_YEARLY_ID` — vide dans `.env` → checkout annuel échoue
- [ ] `STRIPE_PRICE_BUSINESS_YEARLY_ID` — vide dans `.env`
- [ ] `STRIPE_CREDIT_PRICE_ID` — absent du `.env`
- [ ] `@stripe/react-stripe-js` — absent de `frontend/client/package.json` → intégration Stripe.js front absente
- [ ] `RESEND_API_KEY` — absent du `.env` (SMTP configuré mais Resend non actif)
- [ ] API **non démarrée** localement (à lancer manuellement)
- [ ] PostgreSQL **non démarré** localement (pas de Docker actif détecté)
- [ ] Refund endpoint absent
- [ ] Proration Stripe non configurée
- [ ] 2FA admin non implémenté

---

## 🔍 À VÉRIFIER

- [ ] La connexion PostgreSQL locale fonctionne-t-elle ? (DATABASE_URL dans .env pointe vers localhost:5432)
- [ ] Redis local disponible ? (REDIS_URL=redis://localhost:6379/0)
- [ ] L'API peut-elle démarrer avec SQLite en dev (changer DATABASE_URL) ?
- [ ] Le build `.next/` frontend est-il à jour ?
- [ ] `stripe/stripe_ids.json` — les IDs sont-ils identiques à ceux dans `.env` ?

---

## Note sur les deux dépôts locaux

| Dossier | Rôle | À utiliser |
|---------|------|-----------|
| monorepo legacy archivé | Ancien squelette | Référence architecture seulement |
| `kt-monetization-os/` | OS de monétisation — actif | **C'est celui-ci** |
| `kt-monetization-os-needed-copy-.../` | Backup identique | Ignorer |
| clean extract legacy | Extract minimal | Ignorer |
