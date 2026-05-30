# COPILOT_PROMPT — Reprise de session Nanovia OS

Colle ce bloc au début d'une nouvelle session GitHub Copilot CLI pour reprendre le projet immédiatement.

---

## PROMPT DE REPRISE

```
Poursuivons le projet Nanovia.

REPO ACTIF : C:\Users\Alienware\nanovia-os\  (repo Nanovia actuel)
(Ne jamais travailler dans le monorepo archivé ni dans un backup local du repo actif.)

STACK :
- Backend : Python 3.14 · FastAPI 0.115.6 · SQLAlchemy 2 async · Alembic · Stripe SDK 11
- Frontend : Next.js 15.5.14 · React 19 · Tailwind · @stripe/react-stripe-js
- DB prod : PostgreSQL 16 | DB dev : SQLite (aiosqlite)
- Cache : Redis 7 | Auth : JWT HS256 + Argon2id
- Infra : Docker · Caddy · Prometheus · Grafana · GitHub Actions

AVANT TOUTE ACTION :
1. Lire .project-context/WORKSTATE.md → état actuel
2. Lire .project-context/KNOWN_BUGS.md → bugs connus
3. Lire .project-context/NEXT_STEPS.md → prochaine étape prioritaire

RÈGLES :
- Ne jamais modifier le monorepo archivé legacy
- Toujours valider les changements avant commit
- Ne jamais committer .env ni de clés live
- Préférer les petits patches ciblés
- Mettre à jour WORKSTATE.md + KNOWN_BUGS.md après chaque tâche
- PYTHONPATH=backend pour tous les imports Python
- Point d'entrée API : backend/api/main.py → uvicorn api.main:app

COMMANDE DE DÉMARRAGE RAPIDE :
  cd C:\Users\Alienware\nanovia-os
  $env:PYTHONPATH = "backend"
  uvicorn api.main:app --reload --host 127.0.0.1 --port 8010

PROCHAINE TÂCHE (vérifier NEXT_STEPS.md pour l'état exact) :
  ÉTAPE 1 : Vérifier que l'API démarre (SQLite si pas de PostgreSQL local)
  ÉTAPE 2 : npm install dans frontend/client (après ajout @stripe/react-stripe-js)
  ÉTAPE 3 : python stripe/setup_stripe.py → copier yearly/credit price IDs dans .env
  ÉTAPE 4 : Tester flow Stripe end-to-end avec stripe listen
```

---

## Rappel des modules business prioritaires

| Module | Fichier backend | Revenu cible |
|--------|----------------|-------------|
| Module 4 — Ghost Agency | `routers/ghost_agency.py` | 500–5000$/mois 🔴 |
| Module 10 — Execution-as-a-Service | squelette seul | 1000–5000$/mois 🔴 |
| Module 1 — AI Personal Operator | `routers/modules.py` | 50–300$/mois 🟡 |
| Module 2 — Content Cloner | `routers/content_cloner.py` | 200–500$/mois 🟡 |

---

## Fichiers modifiés lors de la dernière session (2026-04-02 — SESSION 2)

| Fichier | Changement |
|---------|-----------|
| `backend/api/models/conversation.py` | JSONB → JSON (SQLite compat) |
| `backend/api/models/content_clone.py` | JSONB → JSON (SQLite compat) |
| `backend/api/models/notification.py` | JSONB → JSON (SQLite compat) |
| `backend/api/database.py` | NullPool SQLite + pool_size PostgreSQL |
| `.env` | STRIPE_PRICE_PRO_YEARLY_ID, STRIPE_PRICE_BUSINESS_YEARLY_ID, STRIPE_CREDIT_PRICE_ID remplis |
| `.project-context/WORKSTATE.md` | Mis à jour (API opérationnelle) |

## ÉTAT AU 2026-04-03 07:53 UTC

### API
- URL : http://127.0.0.1:8010
- Status : ✅ running (PID 5724, sans --reload)
- DB : SQLite dev (dev.db)
- Stripe : TEST mode

### Auth flow — état des routes
| Route | Exposée | Bug connu |
|---|---|---|
| /register | ✅ | ⚠️ retourne UserPublic au lieu de TokenResponse |
| /login | ✅ | ✅ correct |
| /refresh | ✅ | ✅ correct |
| /me | ✅ | ✅ correct |
| /logout | ✅ | ✅ correct |
| /forgot-password | ❌ 404 | Code présent, serveur pas rechargé |
| /reset-password | ❌ 404 | Code présent, serveur pas rechargé |

### Bugs en attente (ordonnés)
1. Restart serveur → exposer forgot/reset (STEP A)
2. _FRONTEND_URL hardcodé → settings.PUBLIC_WEB_URL (STEP B)
3. api.ts request() inexistant → apiFetch() (STEP C)
4. /register retourne UserPublic → TokenResponse (STEP D)

## Fichiers modifiés — Session 3 (2026-04-03)

| Fichier | Changement |
|---|---|
| `backend/api/routers/auth.py` | Ajout forgot-password + reset-password endpoints |
| `backend/api/schemas/auth.py` | Ajout ForgotPasswordRequest + ResetPasswordRequest |
| `backend/api/models/user.py` | Ajout password_reset_token + password_reset_expires |
| `backend/api/services/email_service.py` | Ajout send_password_reset_email() |
| `frontend/client/app/login/page.tsx` | Show/hide password, lien forgot, spinner, ARIA |
| `frontend/client/app/register/page.tsx` | Password strength, confirm, CGU checkbox |
| `frontend/client/app/forgot-password/page.tsx` | Nouvelle page (anti-enumeration) |
| `frontend/client/app/reset-password/page.tsx` | Nouvelle page (token URL, validation) |
| `frontend/client/lib/api.ts` | Ajout forgotPassword() + resetPassword() |
| `.project-context/WORKSTATE.md` | Mis à jour |

## Fichiers modifiés — Session 2 (2026-04-02 soir)

| Fichier | Changement |
|---|---|
| `backend/api/models/conversation.py` | JSONB → JSON |
| `backend/api/models/content_clone.py` | JSONB → JSON |
| `backend/api/models/notification.py` | JSONB → JSON |
| `backend/api/database.py` | NullPool SQLite / pool_size PostgreSQL |
| `.env` | Stripe yearly IDs + credit price ID remplis |

## Fichiers modifiés — Session 1 (2026-04-02)

| Fichier | Changement |
|---|---|
| `backend/api/models/user.py` | Ajout credits: int |
| `backend/api/services/billing_service.py` | Credit ledger + _write_audit() |
| `backend/api/routers/mobile.py` | VIP KPIs avec vraies métriques DB |
| `stripe/setup_stripe.py` | Prix yearly + credit pack |
| `frontend/client/package.json` | @stripe/react-stripe-js ajouté |
| `.project-context/` | 7 fichiers créés |


- **URL** : http://127.0.0.1:8010
- **Status** : ✅ `/health` → 200 OK
- **DB** : SQLite dev (`dev.db` créé automatiquement)
- **Stripe** : TEST mode, tous les price IDs en place

## Fichiers modifiés lors de la session 1 (2026-04-02)

| Fichier | Changement |
|---------|-----------|
| `backend/api/models/user.py` | Ajout champ `credits: int` |
| `backend/api/services/billing_service.py` | Credit ledger complet + audit logs + `_write_audit()` |
| `backend/api/routers/mobile.py` | VIP KPIs avec vraies métriques DB (usage réel) |
| `stripe/setup_stripe.py` | Prix yearly (PRO/BUSINESS) + credit pack ($9.99/100 crédits) |
| `frontend/client/package.json` | Ajout `@stripe/react-stripe-js` + `@stripe/stripe-js` |
| `.env` | Ajout placeholders `STRIPE_PRICE_PRO_YEARLY_ID`, `STRIPE_PRICE_BUSINESS_YEARLY_ID`, `STRIPE_CREDIT_PRICE_ID`, `RESEND_API_KEY` |
| `.project-context/` | Créé : PROJECT_TREE, PROJECT_MAP, RUNBOOK, WORKSTATE, NEXT_STEPS, KNOWN_BUGS, COPILOT_PROMPT |

