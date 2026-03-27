# KT Monetization OS — GitHub Copilot Instructions
# Ces règles s'appliquent à TOUS les fichiers de ce repo

## Identité du projet
Tu travailles sur **KT Monetization OS** — un SaaS IA à 10 modules sur tkverse.ca.
- Backend: FastAPI + Python 3.11 + PostgreSQL + Redis
- Frontend: Next.js 14 + TypeScript
- Infra: Docker + Caddy + OVH VPS (167.114.155.166)
- Repo: github.com/Trudelinc2895/kt-monetization-os

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