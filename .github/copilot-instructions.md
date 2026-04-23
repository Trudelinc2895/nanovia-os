# Nanovia OS — GitHub Copilot Instructions
# Ces règles s'appliquent à TOUS les fichiers de ce repo

## Identité du projet
Tu travailles sur **Nanovia OS** — un SaaS IA à 10 modules sur nanovia.ca.
- Backend: FastAPI + Python 3.11 + PostgreSQL + Redis
- Frontend: Next.js 14 + TypeScript
- Infra: Docker + Caddy + OVH VPS (host configuré via secrets/env de déploiement)
- Repo actuel: remote GitHub du projet Nanovia

## Règles de code OBLIGATOIRES

### Python / FastAPI
- Toujours utiliser **async/await** (SQLAlchemy 2 async, httpx, etc.)
- Passwords: **Argon2id uniquement** — jamais bcrypt, jamais MD5/SHA
- JWT: PyJWT HS256, access=30min, refresh=7j
- Validation: Pydantic v2 strict — jamais de `Any` sans justification
- Imports: absolus uniquement (`from backend.api.models import User`)
- Secrets: toujours depuis `os.getenv()` — jamais hardcodés
- Logging: `structlog` avec level/timestamp/trace_id
- Exceptions: handlers FastAPI structurés (jamais de 500 nus)
- Tests: pytest + httpx AsyncClient — couverture >80%

### TypeScript / Next.js
- `"use client"` seulement quand nécessaire (préférer Server Components)
- Fetch API ou axios avec types stricts — jamais `any`
- Variables d'env: `NEXT_PUBLIC_` pour client, env vars serveur pour secrets
- Erreurs: toujours gérées — jamais de `.catch(console.error)` seul
- Components: PascalCase, hooks: camelCase avec `use` prefix

### Docker / Infra
- Ports internes: `expose` uniquement — JAMAIS `ports: 0.0.0.0:PORT`
- Seul Caddy expose 80/443 publiquement
- Multi-stage builds obligatoires pour images de production
- `restart: unless-stopped` sur tous les services

### Sécurité (BLOQUANT — ne jamais violer)
- Zéro secret dans le code (pas de `sk_live_`, `whsec_`, `-----BEGIN`)
- Input validation stricte sur TOUS les endpoints (jamais de trust implicite)
- SQL: ORM uniquement (SQLAlchemy) — jamais de `f"SELECT ... {user_input}"`
- CORS: liste blanche explicite — jamais `allow_origins=["*"]` en prod
- Rate limiting: Redis-based sur tous les endpoints publics

## Structure des modules IA
```
modules/
  module-{N}-{nom}/
    __init__.py
    router.py      ← FastAPI router (préfixe /api/v1/modules/{nom})
    service.py     ← logique métier
    schemas.py     ← Pydantic models
    prompts/       ← system prompts
    README.md      ← doc du module
```

## Convention de nommage
- Branches: `feature/module-N`, `fix/description`, `chore/description`
- Commits: `feat(scope): description` | `fix(scope):` | `docs:` | `chore:`
- Variables Python: snake_case | Classes: PascalCase | Constants: UPPER_SNAKE
- Variables TS: camelCase | Components: PascalCase | Types: PascalCase

## Réponses attendues de Copilot
1. Code complet et fonctionnel (pas de `# TODO: implement this`)
2. Imports inclus
3. Gestion des erreurs toujours présente
4. Types stricts (pas de `Any` Python, pas de `any` TypeScript)
5. Commentaires UNIQUEMENT sur la logique non évidente

## Sécurité — RÈGLES ABSOLUES (s appliquent à TOUS les projets)

### Jamais faire
- ❌ Committer `.env`, clés, tokens, passwords dans le code
- ❌ `PasswordAuthentication yes` sur SSH
- ❌ `ports:` sur containers internes (utiliser `expose:`)
- ❌ `privileged: true` sur containers
- ❌ Credentials hardcodés (même temporaires)
- ❌ `origins=["*"]` en CORS production
- ❌ `|| true` après des scans de sécurité critiques
- ❌ Installer nftables sur ce VPS (conflit UFW)

### Toujours faire
- ✅ Secrets via `os.getenv()` ou variables GitHub Actions Secrets
- ✅ Argon2id pour les passwords (jamais bcrypt seul, jamais MD5)
- ✅ JWT access ≤ 30min, refresh ≤ 30 jours
- ✅ Rate limiting sur tous les endpoints auth
- ✅ Validation Pydantic stricte sur tous les inputs
- ✅ `restart: unless-stopped` sur tous les containers
- ✅ Exécuter `bash docs/SECURITY_CHECKLIST.md` avant tout deploy prod

### Pour chaque nouveau projet
1. Copier `.github/workflows/security.yml` → scanner auto SAST + secrets + containers
2. Créer `.env.example` avec toutes les variables (valeurs vides)
3. Ajouter `.env` dans `.gitignore` en premier commit
4. Générer tous les secrets: `openssl rand -hex 32`
5. Activer Dependabot via `.github/dependabot.yml`

### Standards secrets (rotation obligatoire tous les 90 jours)
- `SECRET_KEY` : `openssl rand -hex 32` (256 bits)
- `POSTGRES_PASSWORD` : `openssl rand -base64 24 | tr -d '=+/'` (176+ bits)
- `REDIS_PASSWORD` : `openssl rand -base64 24 | tr -d '=+/'`
- Clés Stripe : renouveler dans Stripe Dashboard → Developers → API Keys

### Commandes audit rapide (copier-coller)
```bash
# Sur VPS
ssh root@${VPS_HOST} "docker ps --format '{{.Names}} {{.Status}}' && curl -s localhost/health && fail2ban-client status sshd | grep banned"

# Localement
trufflehog git file://. --only-verified
bandit -r backend/ --severity-level high
```
