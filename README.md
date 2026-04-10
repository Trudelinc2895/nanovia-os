# KT Monetization OS

> **Production-grade SaaS platform** for AI-powered business automation modules.
> Built with FastAPI + Next.js · Stripe billing · Argon2id auth · Redis rate limiting

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/Python-3.14%2B-brightgreen)](https://python.org)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com)

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

**KT Monetization OS** is a full-stack SaaS platform designed to monetize AI-powered automation modules under the `tkverse.ca` brand.

**Core value proposition:**
- AI operator platform with tiered subscription billing
- Modular AI tools (chat, content cloning, ghost agency, orchestration)
- Usage-based overage billing with credit system
- Feature gating by subscription tier
- Real-time analytics and gamification milestones

**Owner:** Kevin Trudel — Trudelinc2895  
**Domain:** tkverse.ca  
**Status:** ✅ Production-ready core · In active development

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT BROWSER                        │
│                    Next.js 15 (App Router)                   │
│              Port 3000 (dev) · tkverse.ca (prod)             │
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

| Feature | Free | Pro ($29/mo) | Business ($99/mo) |
|---------|------|-------------|-------------------|
| AI Messages/month | 50 | 2,000 | Unlimited |
| Storage | 1 GB | 10 GB | 100 GB |
| Team Seats | 1 | 5 | 25 |
| API Access | ❌ | ✅ | ✅ |
| White Label | ❌ | ❌ | ✅ |
| Advanced Analytics | ❌ | ✅ | ✅ |
| Custom Modules | ❌ | ❌ | ✅ |
| Automation | ❌ | ✅ | ✅ |
| Data Export | ❌ | ✅ | ✅ |
| Priority Support | ❌ | ❌ | ✅ |
| Early Access | ❌ | ❌ | ✅ |
| Annual Discount | — | -20% | -20% |
| Free Trial | — | 14 days | 7 days |

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
| Python | 3.14+ | Runtime |
| FastAPI | 0.115 | REST API framework |
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
kt-monetization-os/
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
│   └── client/
│       ├── app/
│       │   ├── page.tsx                    # Homepage + pricing
│       │   ├── login/page.tsx              # Login form
│       │   ├── register/page.tsx           # Registration form
│       │   ├── forgot-password/page.tsx    # Forgot password flow
│       │   ├── reset-password/page.tsx     # Token-based password reset
│       │   ├── not-found.tsx               # 404 page
│       │   ├── error.tsx                   # Error boundary
│       │   └── dashboard/
│       │       ├── page.tsx                # Main dashboard + entitlements
│       │       ├── billing/page.tsx        # Billing dashboard (full)
│       │       ├── analytics/page.tsx      # Analytics + milestones
│       │       └── chat/page.tsx           # AI chat interface
│       ├── lib/
│       │   ├── api.ts                      # API client + all typed helpers
│       │   └── auth-context.tsx            # Auth state (JWT in memory)
│       ├── next.config.ts                  # Security headers, CSP, HSTS
│       ├── tailwind.config.js
│       └── package.json
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

- Python 3.14+
- Node.js 20+
- Redis (optional — rate limiting fails open)
- A Stripe account (test mode for dev)

### 1. Clone

```bash
git clone https://github.com/Trudelinc2895/kt-monetization-os.git
cd kt-monetization-os
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Copy env template
copy .env.example .env         # Windows
# cp .env.example .env         # Linux/Mac

# Edit .env with your values (see Environment Variables section)

# Run backend
$env:PYTHONPATH = "backend"
uvicorn api.main:app --host 127.0.0.1 --port 8010 --reload
```

API docs available at: `http://127.0.0.1:8010/docs` *(dev mode only)*

### 3. Frontend Setup

```bash
cd frontend/client

# Install dependencies
npm install

# Copy env template
copy .env.local.example .env.local   # Windows
# cp .env.local.example .env.local   # Linux/Mac

# Edit .env.local with your values

# Run frontend
npm run dev
```

Frontend available at: `http://localhost:3000`

### 4. Database Setup

```bash
cd backend

# Run migrations
alembic upgrade head
```

---

## Environment Variables

### Backend — `.env`

```bash
# App
APP_ENV=development
APP_NAME="KT Monetization OS"
PUBLIC_WEB_URL=http://localhost:3000
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

# CORS (comma-separated)
ALLOWED_ORIGINS_RAW=http://localhost:3000,http://localhost:3020
```

### Frontend — `.env.local`

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8010
```

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
"white_label"         # Remove KT branding
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
# One-shot install (see infra/scripts/)
bash infra/scripts/install.sh

# Or manually with Docker Compose
cp .env.example .env
# Edit .env with prod values
docker-compose up -d
```

### Architecture (Production)

```
Internet → Caddy (TLS) → FastAPI :8010
                       → Next.js :3000
```

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

# Test API health
curl http://127.0.0.1:8010/api/v1/health
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

MIT © 2025 Kevin Trudel — [tkverse.ca](https://tkverse.ca)

---

## Contributing

This is a private commercial project. Contributions by invitation only.

---

*Built with GitHub Copilot · Powered by FastAPI + Next.js · Billed by Stripe*
