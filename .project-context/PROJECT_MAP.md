# PROJECT MAP — KT Monetization OS

## Identité
- **Domaine :** tkverse.ca
- **Owner :** Kevin Trudel (trudelinc11@gmail.com)
- **Mode :** SaaS multi-modules — production-grade, budget < $10/mois
- **Repo :** https://github.com/Trudelinc2895/kt-monetization-os

---

## Stack Technique

| Couche | Technologie | Version |
|--------|-------------|---------|
| Backend | Python + FastAPI | 3.14 / 0.115.6 |
| ORM | SQLAlchemy async | 2.0.36 |
| DB prod | PostgreSQL | 16 |
| DB dev | SQLite (aiosqlite) | via DATABASE_URL |
| Cache | Redis | 7 |
| Auth | JWT (HS256) + Argon2id | python-jose + argon2-cffi |
| Paiement | Stripe SDK | 11.4.1 |
| Email | Resend API (httpx) | fallback SMTP |
| Frontend web | Next.js + React | 15.5.14 / 19 |
| Frontend mobile | React Native (Expo) | — |
| Reverse proxy | Caddy | auto-TLS |
| Monitoring | Prometheus + Grafana | — |
| CI/CD | GitHub Actions | — |
| Secrets prod | HashiCorp Vault | — |
| LLM local | Ollama (llama3/mistral) | — |
| LLM fallback | OpenAI GPT-4o | — |

---

## Architecture Réseau

```
INTERNET ──HTTPS──► CADDY :443 (TLS auto, rate-limit, security headers)
                         │
           ┌─────────────┼──────────────┐
        :3000          :3020          :8010
      Web App        Admin Panel     FastAPI API
     (Next.js)       (Next.js)          │
                                   :8020 AI Orchestrator
                                   :5432 PostgreSQL
                                   :6379 Redis
                                   :8200 Vault
                                   :11434 Ollama (client)
                                   :11435 Ollama (admin)
                                   :9090 Prometheus
                                   :3030 Grafana (monitor.tkverse.ca)
```

---

## Routes API

### Auth — `/api/v1/auth/`
| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/register` | Inscription |
| POST | `/login` | Connexion → JWT |
| POST | `/refresh` | Refresh token |
| GET | `/me` | Profil courant |
| POST | `/logout` | Révocation token |

### Billing — `/api/v1/billing/`
| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/plans` | Catalogue plans (public) |
| GET | `/subscription` | Abonnement actuel (auth) |
| GET | `/entitlements` | Droits d'accès calculés (auth) |
| GET | `/usage` | Usage mensuel |
| POST | `/checkout-session` | Créer session Stripe Checkout |
| POST | `/portal-session` | Ouvrir portail Stripe |
| POST | `/credits/purchase` | Achat pack crédits |
| POST | `/webhook` | Webhook Stripe (sig-verified) |

### Modules — `/api/v1/`
| Préfixe | Module |
|---------|--------|
| `/modules/` | Module 1 — AI Personal Operator |
| `/ghost-agency/` | Module 4 — Ghost Automation Agency |
| `/content-cloner/` | Module 2 — Content Cloner |
| `/orchestrate/` | AI Orchestrator |
| `/mobile/` | Endpoints mobiles |
| `/health`, `/ready` | Health checks |

---

## Plans & Pricing

| Plan | Prix/mois | Messages/mois | Conversations | Modules actifs |
|------|-----------|---------------|---------------|----------------|
| FREE | $0 | 50 | 5 | 1 |
| PRO | $29 | 1 000 | 100 | 5 |
| BUSINESS | $99 | Illimité | Illimité | 10 |

**Stripe Price IDs (TEST) :**
- PRO monthly: `price_1TErAjARjyNV3UuRe1cikOz4`
- BUSINESS monthly: `price_1TErAjARjyNV3UuRxxcyylnI`
- Yearly: ⚠️ non configurés

---

## Modules Business (10 modules)

| # | Module | Revenu cible | Priorité | Backend router |
|---|--------|-------------|---------|----------------|
| 1 | AI Personal Operator | 50–300$/mois | 🟡 Haute | `routers/modules.py` |
| 2 | Content Cloner Engine | 200–500$/mois | 🟡 Haute | `routers/content_cloner.py` |
| 3 | Micro-SaaS Invisible | 9–49$/user/mois | 🟢 Moyen | squelette seul |
| 4 | Ghost Automation Agency | 500–5000$/mois | 🔴 PRIORITAIRE | `routers/ghost_agency.py` |
| 5 | AI Decision Engine | 47–200$/session | 🟢 Moyen | squelette seul |
| 6 | Knowledge Weapon System | 27–499$/produit | 🟢 Moyen | squelette seul |
| 7 | Digital Leverage Builder | 7–297$ one-shot | 🟡 Haute | squelette seul |
| 8 | AI Reverse Engineering | 500–2000$/audit | 🟢 Moyen | squelette seul |
| 9 | Hyper-Personalized Offer | 19–99$/mois | 🟢 Moyen | squelette seul |
| 10 | Execution-as-a-Service | 1000–5000$/mois | 🔴 PRIORITAIRE | squelette seul |

---

## Base de Données — Tables ORM

| Table | Fichier | Rôle |
|-------|---------|------|
| `users` | models/user.py | Comptes, plan, stripe_customer_id |
| `subscriptions` | models/subscription.py | État Stripe, period_start/end |
| `conversations` | models/conversation.py | Historique chat AI |
| `ghost_agency_campaigns` | models/ghost_agency.py | Campagnes outreach |
| `content_clones` | models/content_clone.py | Contenus repurposés |
| `usage_records` | models/usage_record.py | Tokens consommés par user/module |
| `audit_logs` | models/audit.py | Trail sécurité |
| `notifications` | models/notification.py | Notifs user |
| `device_sessions` | models/device_session.py | Auth mobile |
| `webhook_events` | models/webhook_event.py | Idempotency Stripe |

---

## Variables d'Env — Statut

| Variable | Statut |
|----------|--------|
| DATABASE_URL | ✅ SET (PostgreSQL) |
| REDIS_URL | ✅ SET |
| JWT_SECRET_KEY | ✅ SET |
| STRIPE_SECRET_KEY | ✅ SET (TEST mode) |
| STRIPE_WEBHOOK_SECRET | ✅ SET |
| STRIPE_PRICE_PRO_MONTHLY_ID | ✅ SET |
| STRIPE_PRICE_BUSINESS_MONTHLY_ID | ✅ SET |
| STRIPE_PRICE_PRO_YEARLY_ID | ❌ VIDE |
| STRIPE_PRICE_BUSINESS_YEARLY_ID | ❌ VIDE |
| STRIPE_CREDIT_PRICE_ID | ❌ VIDE (absent) |
| OPENAI_API_KEY | ✅ SET |
| RESEND_API_KEY | ❌ VIDE (absent — SMTP configuré à la place) |
| TELEGRAM_BOT_TOKEN | ✅ SET |

---

## Dépendances Clés (backend/requirements.txt)

```
fastapi==0.115.6        stripe==11.4.1
uvicorn[standard]        sqlalchemy==2.0.36
pydantic==2.10.6         psycopg[binary]==3.2.3
pydantic-settings        redis==5.2.1
python-jose[cryptography] argon2-cffi==23.1.0
bcrypt==4.2.1            httpx==0.28.1
alembic==1.14.0          prometheus-fastapi-instrumentator
```

## Dépendances Frontend (frontend/client/package.json)

```
next==15.5.14   react==19.0.0   tailwindcss==3.4.1
```
⚠️ **MANQUANT :** `@stripe/react-stripe-js` et `@stripe/stripe-js`
