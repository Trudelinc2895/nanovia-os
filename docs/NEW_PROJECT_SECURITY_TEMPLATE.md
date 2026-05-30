# 🔐 TEMPLATE SÉCURITÉ — NOUVEAU PROJET KT
> Copier ce fichier dans chaque nouveau projet. Remplir toutes les sections.
> Ce template impose les standards de sécurité minimaux obligatoires.

---

## 1. INITIALISATION SÉCURISÉE

```bash
# Créer un nouveau projet sécurisé en 5 minutes
PROJECT_NAME="mon-projet"
mkdir $PROJECT_NAME && cd $PROJECT_NAME
git init
git branch -M main

# .gitignore minimal obligatoire
cat > .gitignore << 'EOF'
.env
.env.*
!.env.example
*.key
*.pem
*.p12
secrets/
.secrets/
__pycache__/
*.pyc
node_modules/
.next/
dist/
build/
*.log
.DS_Store
EOF

# Structure minimale
mkdir -p .github/workflows src tests infra/docker docs

# Copier les templates
cp /path/to/nanovia-os/.github/workflows/security.yml .github/workflows/
cp /path/to/nanovia-os/docs/SECURITY_CHECKLIST.md docs/
```

## 2. .env.example OBLIGATOIRE

```bash
# Toujours créer .env.example avec toutes les variables (sans valeurs)
cat > .env.example << 'EOF'
# ⚠️ Copier vers .env et remplir — JAMAIS committer .env

# App
APP_ENV=production
SECRET_KEY=REPLACE_WITH_openssl_rand_-hex_32
REFRESH_SECRET_KEY=REPLACE_WITH_openssl_rand_-hex_32

# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=REPLACE_ME
POSTGRES_USER=REPLACE_ME
POSTGRES_PASSWORD=REPLACE_WITH_openssl_rand_-base64_24

# Redis
REDIS_PASSWORD=REPLACE_WITH_openssl_rand_-base64_24

# Domain
DOMAIN=yourdomain.com
ACME_EMAIL=admin@yourdomain.com

# External APIs
STRIPE_SECRET_KEY=REPLACE_WITH_STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET=REPLACE_WITH_STRIPE_WEBHOOK_SECRET
OPENAI_API_KEY=REPLACE_WITH_OPENAI_API_KEY

# Monitoring
TELEGRAM_BOT_TOKEN=REPLACE_ME
TELEGRAM_CHAT_ID=REPLACE_ME
GRAFANA_ADMIN_PASSWORD=REPLACE_WITH_openssl_rand_-base64_16
EOF
```

## 3. DOCKER COMPOSE SÉCURISÉ (template)

```yaml
# docker-compose.prod.yml — Template sécurisé
version: "3.9"

networks:
  app-net:
    driver: bridge
    internal: false  # Changer à true pour réseaux strictement internes

x-restart: &restart
  restart: unless-stopped

x-no-root: &no-root
  security_opt:
    - no-new-privileges:true

services:
  # ── Reverse Proxy (seul service public) ──────────────────
  caddy:
    image: caddy:2.8-alpine
    <<: [*restart, *no-root]
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./infra/docker/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks: [app-net]
    env_file: .env

  # ── Application API ──────────────────────────────────────
  api:
    build:
      context: .
      dockerfile: infra/docker/api.Dockerfile
    <<: [*restart, *no-root]
    expose: ["8010"]          # JAMAIS ports: ici
    networks: [app-net]
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    read_only: false          # Mettre true si possible
    tmpfs: [/tmp]

  # ── PostgreSQL ───────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    <<: *restart
    expose: ["5432"]          # JAMAIS ports: ici
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_INITDB_ARGS: "--auth-host=scram-sha-256"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks: [app-net]
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── Redis ────────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    <<: *restart
    expose: ["6379"]
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 256mb
    networks: [app-net]
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  caddy_data:
  caddy_config:
  postgres_data:
```

## 4. CADDYFILE HTTPS (template)

```caddyfile
{
    servers {
        trusted_proxies static private_ranges
    }
}

(security_headers) {
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Frame-Options DENY
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        -Server
        -X-Powered-By
    }
}

{$DOMAIN} {
    reverse_proxy web:3000
    import security_headers
    encode gzip
}

api.{$DOMAIN} {
    reverse_proxy api:8010
    import security_headers
}
```

## 5. GITHUB ACTIONS OBLIGATOIRES

Copier depuis `nanovia-os/.github/workflows/security.yml` :
- Gitleaks + TruffleHog (secrets)
- Bandit + pip-audit (SAST Python)
- CodeQL (analyse sémantique)
- Trivy (containers)
- Dependency Review (PRs)

## 6. COMMANDES DE GÉNÉRATION DE SECRETS

```bash
# Générer tous les secrets d un coup
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "REFRESH_SECRET_KEY=$(openssl rand -hex 32)"
echo "POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '=+/')"
echo "REDIS_PASSWORD=$(openssl rand -base64 24 | tr -d '=+/')"
echo "GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16 | tr -d '=+/')"
```

## 7. BRANCH PROTECTION (GitHub Settings)

Pour chaque repo `main` branch:
- ✅ Require pull request before merging
- ✅ Require status checks (security workflow)
- ✅ Require branches to be up to date
- ✅ Do not allow bypassing the above settings

## 8. DEPENDABOT (`.github/dependabot.yml`)

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels: ["security", "dependencies"]

  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "docker"
    directory: "/infra"
    schedule:
      interval: "weekly"
```

