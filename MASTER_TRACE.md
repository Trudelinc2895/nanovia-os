# 🧠 MASTER TRACE — KT Monetization OS
**Owner:** Kevin Trudel (@Trudelinc2895)
**Repo:** https://github.com/Trudelinc2895/kt-monetization-os
**Domain:** tkverse.ca | **Email:** trudelinc11@gmail.com
**Updated:** 2026-03-25 | **Budget:** $0–10 USD
**Mode:** SAAS EXPERT GENIUS OPERATOR — production-grade

---

## CATÉGORIE 1 — MODULES BUSINESS (10 modules)

| # | Module | Branch | Revenu cible | Priorité |
|---|--------|--------|-------------|---------|
| 1 | AI Personal Operator | module-1-ai-operator | 50–300$/mois | 🟡 Haute |
| 2 | Content Cloner Engine | module-2-content-cloner | 200–500$/mois | 🟡 Haute |
| 3 | Micro-SaaS Invisible | module-3-micro-saas | 9–49$/user/mois | 🟢 Moyen |
| 4 | Ghost Automation Agency | module-4-ghost-agency | 500–5000$/mois | 🔴 PRIORITAIRE |
| 5 | AI Decision Engine | module-5-ai-decision | 47–200$/session | 🟢 Moyen |
| 6 | Knowledge Weapon System | module-6-knowledge-weapon | 27–499$/produit | 🟢 Moyen |
| 7 | Digital Leverage Builder | module-7-digital-leverage | 7–297$ one-shot | 🟡 Haute |
| 8 | AI Reverse Engineering | module-8-reverse-engineering | 500–2000$/audit | 🟢 Moyen |
| 9 | Hyper-Personalized Offer | module-9-offer-generator | 19–99$/mois | 🟢 Moyen |
| 10 | Execution-as-a-Service | module-10-execution-service | 1000–5000$/mois | 🔴 PRIORITAIRE |

### Détails Module 4 — Ghost Automation Agency ⭐
- Niche: agents immobiliers, e-commerce, PME
- Stack: Make.com (free) + Python + OpenAI API
- Fichiers: `modules/module-4-ghost-agency/`
- Cold outreach: `cold_outreach_script.md`
- Objectif J1–7: 1er client à 500$

### Détails Module 1 — AI Personal Operator
- Prompt système: `shared/prompts/module1_system_prompt.md`
- Stack: FastAPI + Ollama (local) + OpenAI fallback
- Offre: 50–300$/mois — "employé digital"

---

## CATÉGORIE 2 — ARCHITECTURE SYSTÈME

```
INTERNET ──HTTPS──► CADDY (TLS auto, rate-limit, headers sécurité)
                         │
           ┌─────────────┼──────────────┐
        :3000          :3020          :8010
      Web App        Admin Panel     FastAPI
     (Next.js)       (Next.js)    ← :8020 AI Orchestrator
                                  ← :5432 PostgreSQL
                                  ← :6379 Redis
                                  ← :8200 Vault
                                  ← :11434 Ollama Client
                                  ← :11435 Ollama Admin
                                  ← :9090 Prometheus
                                  ← :3030 Grafana
```

### Séparation User / Admin
| Couche | Client (user) | Opérateur (Kevin) |
|--------|--------------|-------------------|
| Frontend | apps/web :3000 | apps/admin :3020 |
| API scope | /api/v1/user/* | /api/v1/admin/* |
| Auth | JWT 30min + refresh | JWT + MFA + IP whitelist |
| AI | Ollama-Client :11434 | Ollama-Admin :11435 |
| DB view | Tenant isolé (RLS) | Vue globale superadmin |

---

## CATÉGORIE 3 — INFRASTRUCTURE & DEVOPS

### Ports Map Complet
| Service | Port | Exposé public | Notes |
|---------|------|--------------|-------|
| Caddy | 80, 443 | ✅ OUI | Seuls ports publics |
| Web (Next.js) | 3000 | ❌ via Caddy | |
| Admin (Next.js) | 3020 | ❌ via Caddy | |
| API (FastAPI) | 8010 | ❌ via Caddy | |
| AI Orchestrator | 8020 | ❌ interne | |
| PostgreSQL | 5432 | ❌ interne | |
| Redis | 6379 | ❌ interne | |
| Vault | 8200 | ❌ interne | |
| Ollama Client | 11434 | ❌ interne | |
| Ollama Admin | 11435 | ❌ interne | |
| Prometheus | 9090 | ❌ interne | |
| Grafana | 3030 | ❌ via Caddy auth | monitor.tkverse.ca |

### Docker Services
Fichier: `infra/docker-compose.prod.yml`
- caddy, web, admin, api, ai-orchestrator
- postgres:16, redis:7, vault, prometheus, grafana
- Healthchecks sur postgres et redis
- Network isolé: kt-net

---

## CATÉGORIE 4 — BASE DE DONNÉES & DATA ENGINEERING

### Tables PostgreSQL
| Table | Rôle |
|-------|------|
| tenants | Multi-tenant isolation |
| users | Comptes avec rôles RBAC |
| subscriptions | Abonnements Stripe liés |
| module_activations | Modules actifs par tenant |
| billing_events | Webhooks Stripe raw + processed |
| events | KPIs, analytics, usage |
| audit_logs | Toutes actions sensibles |
| sessions | Refresh tokens |
| ai_memory | Mémoire persistante par user/module |

Fichier complet: `database/schema.sql`

### Row Level Security
- RLS activé sur users, subscriptions, module_activations, events, ai_memory
- Isolation via `app.tenant_id` PostgreSQL setting

### Redis Usage
- `session:{user_id}` → JWT metadata (TTL 24h)
- `ratelimit:{ip}:{route}` → compteur rate-limiting
- `cache:{hash}` → cache réponses API (TTL 5min)
- `queue:tasks` → tâches async

---

## CATÉGORIE 5 — SÉCURITÉ & PIPELINES

### 10 Couches de Sécurité
1. UFW: ports 22/80/443 uniquement
2. Fail2ban: brute force SSH/HTTP
3. Caddy: TLS auto + security headers
4. JWT RS256: short-lived access + refresh
5. Vault: secrets chiffrés, jamais en .env prod
6. Redis rate-limiting par IP et user
7. Pydantic: validation input/output stricte
8. RLS PostgreSQL: isolation tenant
9. Audit log: toutes actions en DB
10. Stripe: signature webhook vérifiée à chaque appel

### Pipeline Sécurité CI
- Bandit (Python SAST)
- npm audit (deps vulns)
- Dependabot (auto-PRs)

### Politiques / Garde-fous
- Jamais de sk_live_ dans le repo
- Jamais de .env committé (dans .gitignore)
- Superadmin Kevin: SSH key + JWT séparé + IP whitelist
- RGPD: DELETE CASCADE sur users, export endpoint

---

## CATÉGORIE 6 — STRIPE & BILLING

### Plans & Prix
| Plan | Prix/mois | Stripe Price ID |
|------|-----------|----------------|
| Starter | $0 | free |
| Pro | $49 | STRIPE_PRICE_PRO_MONTHLY_ID |
| Business | $149 | STRIPE_PRICE_BUSINESS_MONTHLY_ID |

### Setup Stripe
```bash
# 1. Remplir .env avec sk_test_...
# 2. Créer produits/prix/webhook:
python stripe/setup_stripe.py
# 3. Copier les IDs générés dans .env
# 4. Tester le flux complet:
stripe listen --forward-to localhost:8010/api/v1/billing/webhook
```

### Webhook Security (CRITIQUE)
Fichier: `backend/api/routers/billing.py`
- `stripe.Webhook.construct_event()` vérifié sur chaque appel
- Idempotency keys sur toutes les créations
- Log de chaque event dans `billing_events`
- Handler d'erreur: return 200 (évite retries inutiles), log pour investigation

### Flux Complet
```
POST /api/v1/billing/checkout-session
→ Stripe Checkout (hosted)
→ Redirect success_url
→ Webhook checkout.session.completed
→ DB: subscription ACTIVE
→ Email confirmation
→ Modules débloqués
```

---

## CATÉGORIE 7 — CI/CD & DÉPLOIEMENT

### Workflows GitHub Actions
| Fichier | Trigger | Action |
|---------|---------|--------|
| ci.yml | push/PR develop,staging,main,modules | lint+test+security |
| deploy.yml | push staging/main | backup+deploy+smoke+notify |

Fichiers: `ci-cd/.github/workflows/`

### Secrets GitHub Actions requis
```
VPS_HOST, VPS_USER, VPS_SSH_PRIVATE_KEY, DEPLOY_PATH
STRIPE_SECRET_KEY, OPENAI_API_KEY
POSTGRES_PASSWORD, JWT_SECRET_KEY
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DOMAIN
```

### Bootstrap VPS (from scratch)
```bash
bash scripts/bootstrap_vps.sh
# Installe: Docker, UFW, fail2ban, clone repo, crée .env
```

---

## CATÉGORIE 8 — MONITORING & KPIs

### Stack
- Prometheus :9090 → scrape API, postgres, redis, caddy
- Grafana :3030 → dashboards (monitor.tkverse.ca)
- Config: `infra/monitoring/prometheus.yml`

### KPIs Business
| KPI | Source | Fréquence |
|-----|--------|-----------|
| MRR | Stripe billing_events | Temps réel |
| Churn rate | subscriptions table | Hebdo |
| DAU/MAU | events table | Temps réel |
| Module usage | events.module_key | Quotidien |
| API p95 latency | Prometheus | Temps réel |
| Error rate 5xx | Prometheus | Temps réel |
| Conversion rate | checkout / signup | Quotidien |

### Alertes Critiques
- API down > 30s → Telegram immédiat
- Error rate > 1% → alerte
- Paiement échoué → email Kevin
- DB connections > 80% → warning
- Disque VPS > 85% → warning

---

## CATÉGORIE 9 — GITHUB BRANCHES & STRUCTURE

### Arborescence Branches (pyramidal)
```
main (prod stable)
  └── staging (pré-prod)
        └── develop (intégration)
              ├── module-1-ai-operator
              ├── module-2-content-cloner
              ├── module-3-micro-saas
              ├── module-4-ghost-agency       ← START HERE
              ├── module-5-ai-decision
              ├── module-6-knowledge-weapon
              ├── module-7-digital-leverage
              ├── module-8-reverse-engineering
              ├── module-9-offer-generator
              ├── module-10-execution-service
              ├── feature/stripe-billing
              ├── feature/auth-jwt
              └── feature/monitoring
```

### Protection des Branches
- `main`: PR obligatoire + 1 approval + CI vert + no force-push
- `staging`: CI vert obligatoire
- `develop`: CI recommandé
- `module-*`: libre, merge via PR vers develop

---

## CATÉGORIE 10 — ROADMAP & ACTIONS IMMÉDIATES

### JOUR 1–2 (Maintenant)
- [x] Repo kt-monetization-os créé
- [x] Structure fichiers complète
- [x] MASTER_TRACE.md généré
- [ ] Pousser sur GitHub + créer toutes les branches
- [ ] Stripe: remplir .env + python stripe/setup_stripe.py
- [ ] Choisir niche module 4 (recommandation: agents immobiliers)

### JOUR 3–4
- [ ] Module 4: 1 workflow Make.com opérationnel
- [ ] Module 1: tester prompt système avec cas réels
- [ ] Backend API: endpoints billing end-to-end
- [ ] Stripe test mode: flux checkout complet

### JOUR 5
- [ ] Test live avec 1 prospect réel
- [ ] Module 3: prototype Streamlit (CV ATS optimizer)
- [ ] Dashboard Grafana: MRR + users actifs

### JOUR 6–7
- [ ] Cold outreach: 20 DMs/emails par jour
- [ ] Passer Stripe en mode LIVE
- [ ] Objectif: 1er client payant (500–1000$)

### OBJECTIF MOIS 1
- Module 4: 2–3 clients × 500–800$/mois = 1000–2400$/mois
- Module 1: 2–3 clients × 150$/mois = 300–450$/mois
- **Total réaliste: 1300–2850$/mois**

---

## CATÉGORIE 11 — ENVIRONNEMENTS & PORTS

| Variable | Dev | Prod |
|----------|-----|------|
| APP_ENV | development | production |
| DATABASE_URL | localhost:5432 | postgres:5432 (Docker) |
| REDIS_URL | localhost:6379 | redis:6379 (Docker) |
| STRIPE_SECRET_KEY | sk_test_... | sk_live_... (via Vault) |
| API_BASE_URL | http://127.0.0.1:8010 | https://api.tkverse.ca |

Fichier de référence: `.env.example`

---

## CATÉGORIE 12 — DNS & DOMAINE

### Cloudflare DNS (tkverse.ca)
| Type | Nom | Valeur | Proxy |
|------|-----|--------|-------|
| A | @ | IP_VPS | ✅ |
| A | www | IP_VPS | ✅ |
| A | api | IP_VPS | ✅ |
| A | admin | IP_VPS | ✅ |
| A | monitor | IP_VPS | ✅ |

### Caddyfile
Fichier: `infra/docker/Caddyfile`
- HTTPS auto via Let's Encrypt
- Security headers (HSTS, X-Frame, CSP)
- Rate limiting sur api.*
- Basic auth sur monitor.*

---

## CATÉGORIE 13 — TENANTS & MULTI-CLIENT

- Modèle: Shared DB + RLS PostgreSQL
- Chaque client = UUID tenant unique
- Modules activables par tenant
- Stripe Customer par tenant
- Rôles: superadmin > admin > user > readonly

---

## CATÉGORIE 14 — AUDIT & COMPLIANCE RGPD

### Endpoints RGPD
- `GET /api/v1/users/me/data` → export complet JSON
- `DELETE /api/v1/users/me` → suppression + CASCADE

### Durées de rétention
| Donnée | Durée |
|--------|-------|
| Audit logs | 2 ans |
| User data | Durée abonnement + 30j |
| Billing events | 7 ans (légal) |
| Sessions Redis | 24h |
| Logs applicatifs | 90j |

---

## CATÉGORIE 15 — STACK TECHNIQUE COMPLÈTE

### Backend
Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic
Stripe SDK · python-jose (JWT) · bcrypt · Redis · LangChain · Ollama

### Frontend
Next.js 15 · TypeScript · Tailwind CSS · shadcn/ui
Zustand · React Query · Stripe.js

### Infrastructure
Docker Compose · Caddy · PostgreSQL 16 + pgcrypto
Redis 7 · HashiCorp Vault · Prometheus · Grafana · GitHub Actions

### AI/ML
Ollama (llama3/mistral — local $0) · OpenAI GPT-4o (fallback)
ChromaDB (vectorstore local $0) · LangChain

### Hébergement (coût total < $10/mois)
| Service | Coût | Rôle |
|---------|------|------|
| VPS Hetzner/OVH | ~5$/mois | Tout héberger |
| Cloudflare | $0 | DNS + CDN |
| GitHub | $0 | Code + CI/CD |
| Stripe | $0 + 2.9% | Billing |
| Gumroad | $0 | Produits digitaux |
| Ollama | $0 | LLM local |
| OpenAI | ~2$/mois | Fallback API |

---

## FICHIERS IMPORTANTS

| Fichier | Rôle |
|---------|------|
| `MASTER_TRACE.md` | Source de vérité — ce fichier |
| `.env.example` | Template variables |
| `database/schema.sql` | Schéma PostgreSQL complet |
| `stripe/setup_stripe.py` | Bootstrap Stripe automatisé |
| `infra/docker-compose.prod.yml` | Stack production Docker |
| `infra/docker/Caddyfile` | Reverse proxy + TLS |
| `infra/monitoring/prometheus.yml` | Métriques |
| `backend/api/main.py` | FastAPI entry point |
| `backend/api/routers/billing.py` | Stripe webhook sécurisé |
| `backend/api/config.py` | Settings centralisés |
| `ci-cd/.github/workflows/ci.yml` | CI pipeline |
| `ci-cd/.github/workflows/deploy.yml` | Deploy + rollback |
| `scripts/bootstrap_vps.sh` | Setup VPS from scratch |
| `shared/prompts/module1_system_prompt.md` | Prompt AI Operator |
| `modules/module-4-ghost-agency/` | Module prioritaire |

---

*Mode: SAAS EXPERT GENIUS OPERATOR*
*Généré par GitHub Copilot CLI — Kevin Trudel / TKVerse*
*Ne jamais committer de secrets. Ce fichier = source de vérité.*
