# Nanovia OS

> **Production-grade SaaS platform** for AI-powered business automation modules.
> Built with FastAPI + Next.js · Stripe billing · Argon2id auth · Redis rate limiting

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-brightgreen)](https://python.org)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688)](https://fastapi.tiangolo.com)

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Monetization Model](#monetization-model)
4. [Tech Stack](#tech-stack)
5. [Project Structure](#project-structure)
6. [Getting Started](#getting-started)
7. [Environment Variables](#environment-variables)
8. [API Reference](#api-reference)
9. [Frontend Pages](#frontend-pages)
10. [Authentication Flow](#authentication-flow)
11. [Billing & Plans](#billing--plans)
12. [AI Modules](#ai-modules)
13. [Security](#security)
14. [Deployment](#deployment)
15. [Development Guide](#development-guide)
16. [Testing](#testing)
17. [Roadmap](#roadmap)

---

## Project Overview

**Nanovia OS** is a full-stack SaaS platform designed to monetize AI-powered automation modules under the `nanovia.ca` brand.

**Core value proposition:**
- AI operator platform with tiered subscription billing
- Modular AI tools (chat, content cloning, ghost agency, orchestration)
- Usage-based overage billing with credit system
- Feature gating by subscription tier
- Real-time analytics and gamification milestones

**Owner:** Kevin Trudel — Trudelinc2895
**Domain:** nanovia.ca
**Status:** Production hardening in progress

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT BROWSER                        │
│                    Next.js 15 (App Router)                   │
│              Port 3000 (dev) · nanovia.ca (prod)             │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS / REST
┌──────────────────────────▼──────────────────────────────────┐
│                    FASTAPI BACKEND                            │
│              Port 8010 · /api/v1/*                           │
│  Auth · Billing · Modules · Analytics · Orchestration        │
└────────┬────────────┬───────────────┬────────────────────────┘
         │            │               │
    ┌────▼───┐   ┌────▼───┐   ┌──────▼──────┐
    │ SQLite │   │  Redis │   │   Stripe     │
    │ (dev)  │   │ Cache  │   │   Billing    │
    │Postgres│   │ Rate   │   │   Webhooks   │
    │ (prod) │   │ Limit  │   └─────────────┘
    └────────┘   └────────┘
         │
    ┌────▼────────────┐
    │  Resend / Email  │
    │  Notifications   │
    └─────────────────┘
```

---

## Monetization Model

### Subscription Tiers

| Feature | Free | Pro ($79/mo) | Business ($149/mo) |
|---------|------|-------------|-------------------|
| AI Messages/month | 50 | 1,000 | Unlimited |
| Storage | 1 GB | 10 GB | 100 GB |
| Team Seats | 1 | 5 | 25 |
| API Access | ❌ | ✅ | ✅ |
| White Label | ❌ | ❌ | ✅ |
| Advanced Analytics | ❌ | ✅ | ✅ |
| Custom Modules | ❌ | ❌ | ✅ |
| Automation | ❌ | ✅ | ✅ |
| Data Export | ❌ | ✅ | ✅ |
| Priority Support | ❌ | ✅ | ✅ |
| Early Access | ❌ | ❌ | ✅ |
| Annual Discount | — | -17% | -17% |
| Free Trial | — | 14 days | 14 days |

### Add-ons (One-time)

| Add-on | Price | What you get |
|--------|-------|-------------|
| API Pack | $5 | +500 API calls |
| Storage 10GB | $5 | +10 GB storage |
| Credits Pack | $4 | +50 overage credits |

### Overage Credits

When a user exceeds their monthly AI message limit:
- If `overage_allowed = True` (Pro+) AND `user.credits > 0` → deducts 1 credit, continues
- If no credits → request blocked with `402 Payment Required`
- System fails **open** if Redis is unavailable (request allowed)

### Gamification Milestones

| Milestone | Trigger |
|-----------|---------|
| First Message | Send first AI message |
| Power User | 100 messages sent |
| Pro Subscriber | Upgrade to Pro |
| Business Subscriber | Upgrade to Business |
| API Pioneer | Make first API call |
| Data Analyst | Export first CSV report |

---

## Tech Stack

### Backend
| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12 | Runtime |
| FastAPI | 0.116 | REST API framework |
| SQLAlchemy | 2.0 | ORM (async) |
| aiosqlite | latest | SQLite async driver (dev) |
| asyncpg | latest | PostgreSQL async driver (prod) |
| Alembic | 1.15 | DB migrations |
| Pydantic v2 | 2.11 | Data validation |
| PyJWT | 2.10 | JWT tokens (HS256) |
| argon2-cffi | 23.1 | Password hashing (Argon2id) |
| Stripe | 11.6 | Payment processing |
| Resend | latest | Transactional email |
| Redis | 5.2 | Rate limiting, cache |
| Prometheus | 7.0 | Metrics instrumentation |

### Frontend
| Technology | Version | Purpose |
|-----------|---------|---------|
| Next.js | 15 | React framework (App Router) |
| TypeScript | 5 | Type safety |
| Tailwind CSS | 3 | Styling |
| React Context | — | Auth state management |

### Infrastructure
| Technology | Purpose |
|-----------|---------|
| Caddy | Reverse proxy + TLS |
| Docker Compose | Container orchestration |
| GitHub Actions | CI/CD pipeline |
| HashiCorp Vault | Secrets management (prod) |
| Prometheus + Grafana | Monitoring + dashboards |
| Alertmanager | Telegram alerts |

---

## Project Structure

```
nanovia/
├── backend/
│   ├── api/
│   │   ├── config.py              # All env vars via pydantic-settings
│   │   ├── database.py            # SQLAlchemy async engine + session
│   │   ├── main.py                # FastAPI app, CORS, rate limiting, routers
│   │   ├── core/
│   │   │   └── deps.py            # Auth + feature gating dependencies
│   │   ├── models/                # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── subscription.py    # billing_interval field
│   │   │   ├── usage_record.py
│   │   │   ├── conversation.py
│   │   │   ├── content_clone.py
│   │   │   ├── notification.py
│   │   │   ├── device_session.py
│   │   │   ├── audit.py
│   │   │   └── webhook_event.py
│   │   ├── schemas/               # Pydantic request/response schemas
│   │   │   ├── auth.py
│   │   │   ├── billing.py         # FeatureGates, UpsellSuggestion, etc.
│   │   │   └── ...
│   │   ├── routers/               # FastAPI route handlers
│   │   │   ├── auth.py            # register, login, refresh, logout, forgot/reset
│   │   │   ├── users.py           # profile, password change
│   │   │   ├── billing.py         # plans, subscription, usage, addons, portal
│   │   │   ├── analytics.py       # history, breakdown, CSV export, milestones
│   │   │   ├── modules.py         # AI module registry + usage gating
│   │   │   ├── orchestrate.py     # AI task orchestration
│   │   │   ├── ghost_agency.py    # Ghost agency AI module
│   │   │   ├── content_cloner.py  # Content cloning AI module
│   │   │   ├── mobile.py          # Mobile-specific endpoints
│   │   │   └── health.py          # /health
│   │   └── services/
│   │       ├── billing_service.py # PLANS_CONFIG, ADDONS_CONFIG, feature logic
│   │       ├── usage_service.py   # check_and_charge_usage(), analytics queries
│   │       └── email_service.py   # Resend transactional emails
│   └── requirements.txt
├── frontend/
│   ├── client/
│   │   ├── app/
│   │   │   ├── page.tsx                    # Homepage + pricing
│   │   │   ├── login/page.tsx              # Login form
│   │   │   ├── register/page.tsx           # Registration form
│   │   │   ├── forgot-password/page.tsx    # Forgot password flow
│   │   │   ├── reset-password/page.tsx     # Token-based password reset
│   │   │   ├── not-found.tsx               # 404 page
│   │   │   ├── error.tsx                   # Error boundary
│   │   │   ├── dashboard/                  # User-facing app
│   │   │   └── admin/                      # Current admin/operator UI routes
│   │   ├── lib/
│   │   │   ├── api.ts                      # API client + all typed helpers
│   │   │   └── auth-context.tsx            # Auth state (JWT in memory)
│   │   ├── next.config.ts                  # Security headers, CSP, HSTS
│   │   ├── tailwind.config.js
│   │   └── package.json
│   └── admin/                              # Optional deploy stub, not the main admin UI
├── stripe/
│   └── setup_stripe.py            # Automated Stripe product/price setup
├── infra/
│   └── scripts/
│       ├── vault-setup.sh         # HashiCorp Vault init
│       └── ...
├── .project-context/              # AI assistant context docs
│   ├── PROJECT_MAP.md
│   ├── RUNBOOK.md
│   ├── WORKSTATE.md
│   ├── KNOWN_BUGS.md
│   ├── NEXT_STEPS.md
│   └── COPILOT_PROMPT.md
├── .gitignore
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.12
- Node.js 20
- Docker Desktop / Docker Engine + Compose plugin (recommended local path)
- A Stripe account (test mode for dev when billing flows are exercised)

### 1. Clone

```bash
git clone <nanovia-repo-url>
cd <nanovia-repo-dir>
```

### 2. Recommended Local Dev Stack (one command)

```bash
copy infra\env\.env.dev.example .env.dev     # Windows
# cp infra/env/.env.dev.example .env.dev     # Linux/Mac

# Edit .env.dev only if you need real Stripe/OpenAI/Resend values locally
docker compose --env-file .env.dev -f infra/docker-compose.dev.yml up --build
```

- Web app: `http://localhost:3000`
- API docs: `http://127.0.0.1:8010/docs`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

Or, use the `make` shortcuts (require Docker):

```bash
make dev-up          # Start the full dev stack (build + up)
make dev-logs        # Live logs from all dev services
make dev-logs-api    # Live logs from the API only
make dev-migrate     # Run Alembic migrations in dev stack
make dev-test        # Run backend pytest in dev stack
make dev-down        # Stop and remove dev containers
```

This is the supported local workflow:
- `frontend/client` serves both the user app and the current admin/operator routes.
- `frontend/admin` stays a separate deploy stub and is not required for local development.
- PostgreSQL + Redis run in containers; the backend uses live reload; the frontend uses Next.js dev mode.

### 3. Manual Local Setup (SQLite fallback)

```bash
# Backend
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # Linux/Mac
pip install -r backend/requirements.txt

copy .env.example .env         # Windows
# cp .env.example .env         # Linux/Mac

# Frontend
cd frontend/client
npm ci
npm run dev
```

For the SQLite fallback, keep `DATABASE_URL=sqlite+aiosqlite:///./dev.db` in `.env` and start the API with:

```bash
$env:PYTHONPATH = "backend"
uvicorn api.main:app --host 127.0.0.1 --port 8010 --reload
```

On Windows, if you are running a PostgreSQL-backed `.env` with Python 3.14, prefer:

```bash
python scripts\run_api_windows.py
```

This avoids the `psycopg` async incompatibility with the default Proactor event loop and also remaps Docker-style local hostnames such as `db`, `postgres`, and `redis` to `127.0.0.1` for direct local runs.

---

## Environment Variables

### Backend — `.env`

The repo now uses one explicit environment strategy:

| File | Purpose | Typical runtime |
|------|---------|-----------------|
| `.env.example` | Lightweight local fallback with SQLite | Manual local run |
| `infra/env/.env.dev.example` | Local Docker dev stack | `infra/docker-compose.dev.yml` |
| `infra/env/.env.example` | Production template | `infra/docker-compose.prod.yml` |
| `infra/env/.env.staging.example` | Isolated staging template | `infra/docker-compose.prod.yml` + `infra/docker-compose.staging.yml` |

Copy `infra/env/.env.dev.example` to `.env.dev` for the Docker dev stack, or copy `.env.example` to `.env` for the manual SQLite fallback.

```bash
# App
APP_ENV=development
APP_NAME="Nanovia OS"
APP_RUNTIME_ENV_FILE=../.env
PUBLIC_WEB_URL=http://localhost:3000
PRIVATE_ADMIN_URL=http://localhost:3020
API_BASE_URL=http://127.0.0.1:8010

# Database
DATABASE_URL=sqlite+aiosqlite:///./dev.db    # dev
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost/ktdb   # prod

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT — generate with: python -c "import secrets; print(secrets.token_hex(64))"
JWT_SECRET_KEY=your-very-long-random-secret-here

# Stripe (use test keys in dev — sk_test_...)
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO_MONTHLY_ID=price_...
STRIPE_PRICE_PRO_YEARLY_ID=price_...
STRIPE_PRICE_BUSINESS_MONTHLY_ID=price_...
STRIPE_PRICE_BUSINESS_YEARLY_ID=price_...
STRIPE_CREDIT_PRICE_ID=price_...
STRIPE_PRICE_ADDON_API_PACK=price_...
STRIPE_PRICE_ADDON_STORAGE_10GB=price_...
STRIPE_PRICE_CREDITS_PACK=price_...

# Email (Resend)
RESEND_API_KEY=re_...

# AI
OPENAI_API_KEY=sk-...
OLLAMA_CLIENT_BASE_URL=http://127.0.0.1:11434

# Private orchestrator (admin-only, disabled by default)
PRIVATE_ORCHESTRATOR_ENABLED=false
PRIVATE_ORCHESTRATOR_UPSTREAM_URL=http://ai-orchestrator:8020
PRIVATE_ORCHESTRATOR_ALLOWED_AGENTS=operator,ghost_agency,decision_engine
ADMIN_ALLOWED_IPS=127.0.0.1/32

# CORS (comma-separated)
ALLOWED_ORIGINS_RAW=http://localhost:3000,http://localhost:3020
```

### Frontend — `.env.local`

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8010
NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED=false
```

When `NEXT_PUBLIC_API_URL` is empty, the frontend uses same-origin `/api` rewrites. That is the default production-safe path and also works in the Docker dev stack.

### Auto-setup Stripe Products

```bash
cd stripe
python setup_stripe.py
```

This creates all products and price IDs in your Stripe account and outputs the IDs to paste into your `.env`.

---

## API Reference

Base URL: `http://127.0.0.1:8010/api/v1`

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register` | — | Register new user |
| POST | `/auth/login` | — | Login → returns access + refresh tokens |
| POST | `/auth/refresh` | Bearer | Refresh access token |
| GET | `/auth/me` | Bearer | Get current user |
| POST | `/auth/logout` | Bearer | Invalidate refresh token |
| POST | `/auth/forgot-password` | — | Send password reset email |
| POST | `/auth/reset-password` | — | Reset password with token |

### Users

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| PUT | `/users/profile` | Bearer | Update profile |
| PUT | `/users/password` | Bearer | Change password |

### Billing

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/billing/plans` | — | List all plans and prices |
| GET | `/billing/subscription` | Bearer | Current subscription |
| GET | `/billing/entitlements` | Bearer | Feature flags + limits |
| GET | `/billing/usage` | Bearer | Current period usage stats |
| GET | `/billing/upsell` | Bearer | Contextual upsell suggestion |
| GET | `/billing/addons` | Bearer | Available add-ons |
| POST | `/billing/addon/checkout` | Bearer | Stripe checkout for add-on |
| POST | `/billing/checkout` | Bearer | Stripe checkout for plan |
| POST | `/billing/portal` | Bearer | Stripe customer portal |
| GET | `/billing/credits` | Bearer | Credit balance |
| POST | `/billing/credits/purchase` | Bearer | Buy credit pack |
| POST | `/billing/webhook` | Stripe sig | Stripe event handler |

### Admin / Operator

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/admin/webhooks` | Admin bearer | Recent Stripe webhook events + status |
| POST | `/admin/webhooks/{stripe_event_id}/reprocess` | Admin bearer | Re-fetch a stored Stripe event and replay it |
| GET | `/admin/users/{user_id}/billing-audit` | Admin bearer | Billing audit trail for one user |
| POST | `/admin/users/{user_id}/resync-subscription` | Admin bearer | Force-sync latest Stripe subscription into local DB |
| GET | `/admin/orchestrator/overview` | Admin bearer | Private orchestrator status/contract (404 when disabled) |
| GET | `/admin/orchestrator/agents` | Admin bearer | Allowlisted private orchestrator agent catalog |

### Analytics

| Method | Endpoint | Auth | Plan |
|--------|----------|------|------|
| GET | `/analytics/history?days=30` | Bearer | Pro+ |
| GET | `/analytics/breakdown?days=30` | Bearer | Free (7d max) / Pro+ |
| GET | `/analytics/export?days=30` | Bearer | Pro+ |
| GET | `/analytics/milestones` | Bearer | All |

### AI Modules

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/modules` | Bearer | List available modules |
| POST | `/modules/{id}/run` | Bearer | Run AI module (usage tracked) |
| POST | `/orchestrate` | Bearer | Orchestrate multi-step task |
| POST | `/ghost-agency/run` | Bearer | Ghost agency AI task |
| POST | `/content-cloner/clone` | Bearer | Clone and rewrite content |

### Health

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | — | API health check |

---

## Frontend Pages

| Route | Description | Auth required |
|-------|-------------|---------------|
| `/` | Homepage + pricing grid | No |
| `/login` | Login form with redirect | No |
| `/register` | Registration form | No |
| `/forgot-password` | Request password reset email | No |
| `/reset-password?token=...` | Reset password with token | No |
| `/dashboard` | Main dashboard + KPIs | ✅ Yes |
| `/dashboard/billing` | Billing management | ✅ Yes |
| `/dashboard/analytics` | Usage analytics | ✅ Yes (Pro+) |
| `/dashboard/chat` | AI chat interface | ✅ Yes |
| `/admin/webhooks` | Admin Stripe webhook status view | ✅ Admin only |
| `/admin/orchestrator` | Private orchestrator slice | ✅ Admin only + feature-flagged |

Admin/operator pages currently live inside `frontend/client`. The separate `frontend/admin` deploy target is still an infrastructure stub and should be treated as optional until it becomes a real standalone app.

---

## Authentication Flow

### Token Strategy

- **Access token**: HS256 JWT · 30 min expiry · stored in JS memory only
- **Refresh token**: HS256 JWT · 30 day expiry · stored in `localStorage`
- **Security**: Access token never touches disk/localStorage → XSS resistant

### Register → Login Flow

```
1. POST /auth/register { email, password, full_name }
   → returns { user, access_token, refresh_token }

2. Frontend stores:
   - access_token in JS memory (_accessToken variable)
   - refresh_token in localStorage

3. Every request: Authorization: Bearer <access_token>

4. On 401: POST /auth/refresh { refresh_token }
   → returns new access_token (auto-injected by api.ts)
```

### Forgot Password Flow

```
1. POST /auth/forgot-password { email }
   → always returns 200 (prevents email enumeration)
   → sends email with link: PUBLIC_WEB_URL/reset-password?token=<secure_token>

2. Token: 32 bytes from secrets.token_urlsafe() · expires 1 hour · single use

3. POST /auth/reset-password { token, new_password }
   → validates token · hashes password (Argon2id) · invalidates token
```

---

## Billing & Plans

### Plan Keys

Plans are identified by lowercase strings: `"free"`, `"pro"`, `"business"`

⚠️ `"starter"` does NOT exist in this codebase.

### Feature Flags (10 gates)

```python
"api_access"          # REST API calls allowed
"white_label"         # Remove Nanovia branding for client delivery
"priority_support"    # Priority queue
"advanced_analytics"  # 30/90 day analytics history
"custom_modules"      # Build custom AI modules
"automation"          # Workflow automation
"team_seats"          # Multiple team members
"data_export"         # CSV export of analytics
"overage_allowed"     # Continue after limit (uses credits)
"early_access"        # Beta features
```

### Overage Credit System

1 credit = 1 extra AI message when monthly limit exceeded.

Credit packs available via one-time Stripe purchase (add-on).

### Webhook Events Handled

- `checkout.session.completed` — activate subscription or add credits
- `customer.subscription.updated` — update plan
- `customer.subscription.deleted` — downgrade to free
- `invoice.payment_failed` — flag account

### Operator Recovery

- Use `GET /api/v1/admin/webhooks` to inspect recent Stripe processing state.
- Use `POST /api/v1/admin/webhooks/{stripe_event_id}/reprocess` to replay a stored event.
- Use `POST /api/v1/admin/users/{user_id}/resync-subscription` to recover a user's latest Stripe state from Stripe when webhook delivery drifted.

---

## AI Modules

All AI module endpoints are protected by:
1. **Authentication** (`current_user` dependency)
2. **Usage check** (`check_and_charge_usage`) — respects plan limits + overage
3. **Feature gating** (`require_feature()`) — plan must have the feature

| Module | Feature gate | Usage tracked |
|--------|-------------|---------------|
| Chat / Messages | — (all plans) | ✅ `ai_messages` |
| Orchestrate | `automation` | ✅ |
| Ghost Agency | `automation` | ✅ |
| Content Cloner | `api_access` | ✅ |

---

## Security

### Implemented

| Layer | Measure |
|-------|---------|
| Passwords | Argon2id (OWASP recommended) · bcrypt fallback for migrated users |
| Tokens | JWT HS256 · access token in memory · refresh in localStorage |
| Rate limiting | 10 req/min auth · 100/min authenticated · 30/min anonymous · fail-open |
| Headers | CSP, HSTS (prod only), X-Frame-Options, Referrer-Policy, Permissions-Policy |
| API docs | Disabled in production (`APP_ENV=production`) |
| Secrets | All via env vars · never hardcoded · `.env` gitignored |
| Database | `dev.db` and all `*.db` in `.gitignore` |
| Webhook | Stripe signature verified before processing |
| Password reset | 32-byte random token · 1h expiry · single use · generic email response |
| Private orchestrator | Admin-only + feature-flagged off by default · read-only status/catalog slice only · no terminal/files/browser/user-impersonation |

### Never Hardcoded

- No IP addresses in source code
- No API keys
- No JWT secrets
- No Stripe keys
- No database credentials

### `.gitignore` protects

```
.env, .env.*, .env.local, .env.prod
*.db, *.sqlite, *.sqlite3, dev.db
```

---

## Deployment

### Quick Start (Ubuntu 24.04)

```bash
# Production (public stack on OVH)
cp infra/env/.env.example .env.production   # or .env for current production host
python3 scripts/validate_runtime_env.py --env-file .env.production --target-env production
docker compose -p nanovia-prod -f infra/docker-compose.prod.yml --env-file .env.production up -d

# Staging (same VPS, isolated path/project, loopback-only ports)
cp infra/env/.env.staging.example .env.staging
python3 scripts/validate_runtime_env.py --env-file .env.staging --target-env staging
docker compose -p nanovia-staging -f infra/docker-compose.prod.yml -f infra/docker-compose.staging.yml --env-file .env.staging up -d
```

### GitHub flow

- `feature/*` branches open PRs into `staging`
- `staging` is the integration branch validated by CI and eligible for staging deploys
- `main` stays production-oriented
- CI and deploy workflows are aligned on `staging` and `main`

### Architecture (Production)

```
Internet → Caddy (TLS) → FastAPI :8010
                       → Next.js :3000
```

- The public app stays on `https://nanovia.ca` with same-origin `/api`.
- The current admin/operator UI lives in `frontend/client/app/admin/*`.
- The separate `admin` container remains a private operational stub in the stack, and the default production `Caddyfile` still does **not** publish a public `admin.` host yet.

### Staging vs production on one OVH VPS

- `main` keeps the current production flow.
- `staging` can deploy to a separate `DEPLOY_PATH` with its own `.env.staging`.
- Production stays on `infra/docker-compose.prod.yml`.
- Staging reuses the same stack plus `infra/docker-compose.staging.yml`, which publishes app ports on loopback-only high ports and skips Caddy.
- `APP_RUNTIME_ENV_FILE` should match the chosen runtime env file (`../.env.production`, `../.env.staging`, or legacy `../.env`).
- Deploys now fail early if the env file still has placeholder secrets, lacks `TOTP_ENCRYPTION_KEY`, or omits the production admin IP allowlist.
- This is **not** zero-downtime; it is safer environment separation for a single-host Compose setup.
- Recommended GitHub Environment secrets/vars per target:
  - secrets: `VPS_HOST`, `VPS_SSH_PRIVATE_KEY`, `DEPLOY_PATH`
  - vars: `APP_DOMAIN`, `PUBLIC_IP`, `STAGING_BIND_ADDRESS`, `STAGING_WEB_PORT`, `STAGING_ADMIN_PORT`, `STAGING_API_PORT`, `STAGING_AI_PORT`

### Staging access

Use SSH tunnels instead of exposing the shared host publicly:

```bash
ssh -L 13000:127.0.0.1:13000 -L 13020:127.0.0.1:13020 -L 18010:127.0.0.1:18010 deploy@YOUR_VPS_HOST
```

- Web: `http://127.0.0.1:13000`
- Admin: `http://127.0.0.1:13020`
- API: `http://127.0.0.1:18010`
- Keep staging on Stripe test keys only.

### Required Services

- PostgreSQL (replace SQLite)
- Redis (rate limiting)
- Resend account (email)
- Stripe account (billing)

### Monitoring

- Prometheus metrics at `/metrics`
- Grafana dashboards in `kpi/`
- Alertmanager → Telegram notifications

---

## Development Guide

### Start Both Services

```bash
# Terminal 1 — Backend
cd kt-monetization-os
$env:PYTHONPATH = "backend"
$env:PYTHONIOENCODING = "utf-8"
uvicorn api.main:app --host 127.0.0.1 --port 8010 --reload

# Terminal 2 — Frontend
cd frontend/client
npm run dev
```

### Common Commands

```bash
# Run DB migrations
cd backend && alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Type-check frontend
cd frontend/client && npx tsc --noEmit

# Lint frontend
npm run lint

# Setup Stripe products (first time)
python stripe/setup_stripe.py

# Test API liveness / readiness
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/api/v1/health/ready
```

### Code Conventions

- Backend: async/await throughout · no sync DB calls
- `await db.commit()` required after every mutation
- `settings.*` always · never hardcode URLs or secrets
- Feature gating via `require_feature("flag_name")` dependency
- Usage tracking via `check_and_charge_usage(current_user, db)`

---

## Testing

### Manual Test Checklist

#### Auth

```bash
# Register
curl -X POST http://127.0.0.1:8010/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"Test1234!","full_name":"Test User"}'

# Login
curl -X POST http://127.0.0.1:8010/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"Test1234!"}'

# Me (replace TOKEN)
curl http://127.0.0.1:8010/api/v1/auth/me \
  -H "Authorization: Bearer TOKEN"

# Forgot password
curl -X POST http://127.0.0.1:8010/api/v1/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com"}'
```

#### Billing

```bash
# Plans (no auth)
curl http://127.0.0.1:8010/api/v1/billing/plans

# Entitlements (auth required)
curl http://127.0.0.1:8010/api/v1/billing/entitlements \
  -H "Authorization: Bearer TOKEN"

# Usage
curl http://127.0.0.1:8010/api/v1/billing/usage \
  -H "Authorization: Bearer TOKEN"
```

#### Analytics

```bash
# Breakdown (last 7 days — all plans)
curl "http://127.0.0.1:8010/api/v1/analytics/breakdown?days=7" \
  -H "Authorization: Bearer TOKEN"

# Milestones
curl http://127.0.0.1:8010/api/v1/analytics/milestones \
  -H "Authorization: Bearer TOKEN"
```

---

## Roadmap

### Completed ✅

- [x] Full auth system (register, login, refresh, logout, forgot/reset password)
- [x] JWT token strategy (memory + localStorage)
- [x] Argon2id password hashing
- [x] Tiered subscription plans (Free / Pro / Business)
- [x] Stripe billing integration (checkout, portal, webhooks)
- [x] Add-ons system (API pack, storage, credits)
- [x] Overage credit billing
- [x] 10 feature flags with plan gating
- [x] Rate limiting (Redis-backed, fail-open)
- [x] Analytics (history, breakdown, CSV export)
- [x] Gamification milestones
- [x] Full billing dashboard (frontend)
- [x] Analytics dashboard (frontend)
- [x] Forgot/reset password pages (frontend)
- [x] Security headers (CSP, HSTS, X-Frame)
- [x] Docs disabled in production
- [x] No hardcoded secrets anywhere
- [x] CI/CD pipeline (GitHub Actions)
- [x] Monitoring (Prometheus + Grafana)

### In Progress 🔄

- [ ] Email notifications (subscription events)
- [ ] Team seats management UI
- [ ] Mobile API endpoints
- [ ] Audit log viewer

### Planned 📋

- [ ] White-label configuration panel
- [ ] Custom module builder (Business tier)
- [ ] Webhook event replay
- [ ] Multi-tenancy support
- [ ] Annual plan checkout flow
- [ ] Admin dashboard
- [ ] Usage alerts (notify at 80% of limit)
- [ ] GDPR data export endpoint
- [ ] Two-factor authentication (TOTP)

---

## License

MIT © 2025 Kevin Trudel — [nanovia.ca](https://nanovia.ca)

---

## Contributing

This is a private commercial project. Contributions by invitation only.

---

*Built with GitHub Copilot · Powered by FastAPI + Next.js · Billed by Stripe*
