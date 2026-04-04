#!/bin/bash
# ============================================================
# KT Monetization OS — Fresh Install Script
# Run on a BRAND NEW Ubuntu 22.04 / 24.04 VPS
#
# Usage:
#   # With domain:
#   bash infra/scripts/fresh-install.sh tkverse.ca admin@tkverse.ca
#
#   # IP only (no domain yet):
#   bash infra/scripts/fresh-install.sh
# ============================================================
set -e

DOMAIN="${1:-}"
ACME_EMAIL="${2:-}"
APP_DIR="/opt/kt-monetization-os"
REPO="https://github.com/Trudelinc2895/kt-monetization-os.git"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
err()  { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   KT Monetization OS — Fresh Install         ║"
echo "║   $([ -n "$DOMAIN" ] && echo "$DOMAIN" || echo 'IP-only mode (no domain)')                   ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── STEP 1: System update + base packages ────────────────────
echo "[1/9] Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    git curl wget ufw fail2ban \
    ca-certificates gnupg lsb-release \
    dnsutils htop vim unzip 2>&1 | tail -3
ok "System packages installed"

# ── STEP 2: Install Docker ────────────────────────────────────
echo "[2/9] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh 2>&1 | tail -5
    systemctl enable docker
    systemctl start docker
    ok "Docker installed: $(docker --version)"
else
    ok "Docker already installed: $(docker --version)"
fi

# ── STEP 3: Configure UFW firewall ───────────────────────────
echo "[3/9] Configuring UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment 'SSH'
ufw allow 80/tcp   comment 'HTTP'
ufw allow 443/tcp  comment 'HTTPS'
ufw --force enable
ok "UFW: SSH/HTTP/HTTPS open, all else blocked"

# ── STEP 4: Configure fail2ban ────────────────────────────────
echo "[4/9] Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd

[sshd]
enabled = true
port    = ssh
maxretry = 3
bantime  = 6h
EOF
systemctl enable fail2ban
systemctl restart fail2ban
ok "fail2ban active (SSH: 3 attempts max, 6h ban)"

# ── STEP 5: Clone repository ─────────────────────────────────
echo "[5/9] Cloning repository..."
if [ -d "$APP_DIR/.git" ]; then
    cd $APP_DIR && git pull origin main 2>&1 | tail -3
    ok "Repo updated: $(git rev-parse --short HEAD)"
else
    git clone $REPO $APP_DIR 2>&1 | tail -3
    ok "Repo cloned: $(cd $APP_DIR && git rev-parse --short HEAD)"
fi
chmod +x $APP_DIR/infra/scripts/*.sh

# ── STEP 6: Create .env if missing ───────────────────────────
echo "[6/9] Setting up .env..."
cd $APP_DIR

MY_IP=$(curl -s https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')

# Determine mode
if [ -n "$DOMAIN" ]; then
    MODE="https"
    API_URL="https://api.$DOMAIN"
    ORIGINS="https://$DOMAIN,https://www.$DOMAIN,https://api.$DOMAIN"
    CADDYFILE_PATH="./docker/Caddyfile"
    EMAIL="${ACME_EMAIL:-admin@$DOMAIN}"
else
    MODE="ip"
    DOMAIN="$MY_IP"
    API_URL="http://$MY_IP"
    ORIGINS="http://$MY_IP"
    CADDYFILE_PATH="./docker/Caddyfile.ip"
    EMAIL="admin@localhost"
    warn "No domain provided — starting in IP-only mode (HTTP)"
fi

if [ ! -f .env ]; then
    # Generate strong secrets
    SECRET_KEY=$(openssl rand -hex 32)
    REFRESH_KEY=$(openssl rand -hex 32)
    TOTP_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || openssl rand -base64 32)
    PG_PASS=$(openssl rand -base64 20 | tr -d '+/=' | head -c 20)
    REDIS_PASS=$(openssl rand -base64 16 | tr -d '+/=' | head -c 16)
    GRAFANA_PASS=$(openssl rand -base64 12 | tr -d '+/=' | head -c 12)
    JWT_KEY=$(openssl rand -hex 32)

    cat > .env << ENVEOF
# ── KT Monetization OS — Environment ──────────────────────
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Mode: $MODE

# Caddy config
CADDYFILE=$CADDYFILE_PATH
DOMAIN=$DOMAIN
ACME_EMAIL=$EMAIL

# App URLs
NEXT_PUBLIC_API_URL=$API_URL
PUBLIC_WEB_URL=$API_URL
ALLOWED_ORIGINS=$ORIGINS
APP_ENV=production

# Database (PostgreSQL via Docker)
DATABASE_URL=postgresql+psycopg://kt_user:\${POSTGRES_PASSWORD}@postgres:5432/kt_monetization
POSTGRES_DB=kt_monetization
POSTGRES_USER=kt_user
POSTGRES_PASSWORD=$PG_PASS

# Redis
REDIS_URL=redis://:$REDIS_PASS@redis:6379/0
REDIS_PASSWORD=$REDIS_PASS

# Auth — auto-generated (DO NOT CHANGE after first start)
SECRET_KEY=$SECRET_KEY
JWT_SECRET_KEY=$JWT_KEY
REFRESH_SECRET_KEY=$REFRESH_KEY
TOTP_ENCRYPTION_KEY=$TOTP_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Stripe — REPLACE WITH YOUR KEYS
STRIPE_SECRET_KEY=stripe_test_REPLACE_ME
STRIPE_PUBLISHABLE_KEY=stripe_public_test_REPLACE_ME
STRIPE_WEBHOOK_SECRET=stripe_webhook_REPLACE_ME
STRIPE_CHECKOUT_SUCCESS_URL=$API_URL/dashboard/billing?success=1
STRIPE_CHECKOUT_CANCEL_URL=$API_URL/dashboard/billing?canceled=1
STRIPE_PORTAL_RETURN_URL=$API_URL/dashboard/billing

# Plan price IDs (run stripe/setup_stripe.py to generate)
STRIPE_PRICE_PRO_MONTHLY_ID=
STRIPE_PRICE_PRO_YEARLY_ID=
STRIPE_PRICE_BUSINESS_MONTHLY_ID=
STRIPE_PRICE_BUSINESS_YEARLY_ID=

# Module price IDs
STRIPE_PRICE_MODULE_OPERATOR=
STRIPE_PRICE_MODULE_CONTENT=
STRIPE_PRICE_MODULE_MICRO_SAAS=
STRIPE_PRICE_MODULE_GHOST=
STRIPE_PRICE_MODULE_DECISION=
STRIPE_PRICE_MODULE_KNOWLEDGE=
STRIPE_PRICE_MODULE_LEVERAGE=
STRIPE_PRICE_MODULE_REVERSE=
STRIPE_PRICE_MODULE_OFFER=
STRIPE_PRICE_MODULE_EXECUTION=

# OpenAI — REPLACE WITH YOUR KEY
OPENAI_API_KEY=sk-REPLACE_ME
OLLAMA_CLIENT_BASE_URL=

# Email (Resend)
RESEND_API_KEY=re_REPLACE_ME
FROM_EMAIL=noreply@$DOMAIN

# Monitoring
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASS
TELEGRAM_BOT_TOKEN=REPLACE_ME
TELEGRAM_CHAT_ID=REPLACE_ME
ENVEOF
    ok ".env generated (mode=$MODE, ip=$MY_IP)"
    warn "⚠  Edit .env: STRIPE_SECRET_KEY + OPENAI_API_KEY required before first use"
else
    # Update mode-specific vars if switching
    sed -i "s|^CADDYFILE=.*|CADDYFILE=$CADDYFILE_PATH|" .env
    sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" .env
    ok ".env already exists — CADDYFILE + DOMAIN updated (mode=$MODE)"
fi

# ── STEP 7: Check DNS ────────────────────────────────────────
echo "[7/9] Checking connectivity..."
DNS_OK=false

if [ "$MODE" = "https" ]; then
    RESOLVED=$(dig +short "$DOMAIN" @8.8.8.8 2>/dev/null | tail -1)
    if [ "$RESOLVED" = "$MY_IP" ]; then
        ok "DNS: $DOMAIN → $MY_IP ✓"
        DNS_OK=true
    else
        warn "DNS not pointing here yet (domain resolves to: '${RESOLVED:-none}', this VPS: $MY_IP)"
        warn "OVH Manager → Zone DNS → add A record: $DOMAIN → $MY_IP"
        warn "Also add: www, api, admin, monitor → $MY_IP"
        warn "Caddy HTTPS will fail until DNS propagates — containers still starting in HTTP fallback"
        # Force Caddyfile.ip until DNS is ready
        sed -i "s|^CADDYFILE=.*|CADDYFILE=./docker/Caddyfile.ip|" .env
        CADDYFILE_PATH="./docker/Caddyfile.ip"
        warn "Switched to Caddyfile.ip (HTTP-only) until DNS is ready"
    fi
else
    ok "IP-only mode — no DNS check needed"
    ok "App will be reachable at: http://$MY_IP"
fi

# ── STEP 8: Build + launch containers ───────────────────────
echo "[8/9] Building and launching containers..."
cd $APP_DIR
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --build 2>&1 | tail -20

echo ""
echo "  Waiting for containers to be ready..."
sleep 20

RUNNING=$(docker ps --filter "status=running" --format "{{.Names}}" | wc -l)
ok "$RUNNING containers running"

# ── Run Alembic migrations ───────────────────────────────────
echo ""
echo "  Running database migrations..."
docker compose -f infra/docker-compose.prod.yml exec -T api alembic upgrade head 2>&1
ok "Migrations applied (alembic upgrade head)"

# ── STEP 9: Final status ─────────────────────────────────────
echo ""
echo "[9/9] ══ FINAL STATUS ══════════════════════════════"
echo ""

for svc in ufw fail2ban docker; do
    STATUS=$(systemctl is-active $svc 2>/dev/null)
    [ "$STATUS" = "active" ] && ok "$svc" || warn "$svc: $STATUS"
done

echo ""
docker ps --format "  {{.Names}}: {{.Status}}" 2>/dev/null

echo ""
echo "  Server IP:   $MY_IP"
if [ "$MODE" = "https" ] && [ "$DNS_OK" = "true" ]; then
    echo "  Mode:        HTTPS (domain: $DOMAIN)"
else
    echo "  Mode:        HTTP-only (IP: $MY_IP)"
fi
echo ""

STRIPE_CONFIGURED=$(grep 'STRIPE_SECRET_KEY' .env | grep -v REPLACE | head -1)
if [ -n "$STRIPE_CONFIGURED" ]; then
    ok "Stripe configured"
else
    warn "STRIPE_SECRET_KEY not yet set in .env"
fi

echo ""
if [ "$MODE" = "https" ] && [ "$DNS_OK" = "true" ]; then
    echo "══ LIVE (HTTPS) ════════════════════════════════"
    echo "  https://$DOMAIN           → Frontend"
    echo "  https://api.$DOMAIN       → FastAPI"
    echo "  https://monitor.$DOMAIN   → Grafana"
    echo "  Grafana: admin / $(grep GRAFANA_ADMIN_PASSWORD .env | cut -d= -f2)"
else
    echo "══ LIVE (HTTP) ══════════════════════════════════"
    echo "  http://$MY_IP             → Frontend"
    echo "  http://$MY_IP/api/v1      → FastAPI"
    echo "  http://$MY_IP/docs        → Swagger (dev)"
    echo ""
    echo "══ TODO (pour activer HTTPS) ═══════════════════"
    if [ -n "${1:-}" ]; then
        echo "  1. OVH Manager → Zone DNS → A record: ${1} → $MY_IP"
        echo "  2. Attendre propagation DNS (5–30 min)"
        echo "  3. Re-run: bash $APP_DIR/infra/scripts/fresh-install.sh ${1}"
    else
        echo "  1. Obtenir un domaine (ex: tkverse.ca)"
        echo "  2. OVH Manager → Zone DNS → A record: domaine → $MY_IP"
        echo "  3. Re-run: bash $APP_DIR/infra/scripts/fresh-install.sh TON_DOMAINE admin@TON_DOMAINE"
    fi
fi
echo ""
echo "══ NEXT STEPS ══════════════════════════════════"
echo "  1. nano $APP_DIR/.env  (ajouter STRIPE_SECRET_KEY + OPENAI_API_KEY)"
echo "  2. docker compose -f infra/docker-compose.prod.yml exec api python scripts/create_admin.py"
echo "  3. cd $APP_DIR && bash infra/scripts/backup.sh  (tester backup)"
echo ""