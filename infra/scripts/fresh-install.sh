#!/bin/bash
# ============================================================
# KT Monetization OS — Fresh Install Script
# Run on a BRAND NEW Ubuntu 24.04 VPS
# Usage: curl -fsSL https://raw.githubusercontent.com/Trudelinc2895/kt-monetization-os/main/infra/scripts/fresh-install.sh | bash
# ============================================================
set -e

DOMAIN="tkverse.ca"
APP_DIR="/opt/kt-monetization-os"
REPO="https://github.com/Trudelinc2895/kt-monetization-os.git"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
err()  { echo -e "${RED}  ✗ $1${NC}"; }

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   KT Monetization OS — Fresh Install         ║"
echo "║   tkverse.ca                                 ║"
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

if [ ! -f .env ]; then
    # Generate strong secrets
    SECRET_KEY=$(openssl rand -hex 32)
    REFRESH_KEY=$(openssl rand -hex 32)
    PG_PASS=$(openssl rand -base64 20 | tr -d '+/=' | head -c 20)
    REDIS_PASS=$(openssl rand -base64 16 | tr -d '+/=' | head -c 16)
    GRAFANA_PASS=$(openssl rand -base64 12 | tr -d '+/=' | head -c 12)

    cat > .env << ENVEOF
# ── KT Monetization OS — Environment ──────────────────────
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)

# Domain
DOMAIN=$DOMAIN
ACME_EMAIL=admin@$DOMAIN
NEXT_PUBLIC_API_URL=https://api.$DOMAIN
ALLOWED_ORIGINS=https://$DOMAIN,https://www.$DOMAIN,https://app.$DOMAIN,https://api.$DOMAIN

# Database
POSTGRES_DB=kt_monetization
POSTGRES_USER=kt_user
POSTGRES_PASSWORD=$PG_PASS

# Redis
REDIS_PASSWORD=$REDIS_PASS

# Auth (auto-generated secure keys)
SECRET_KEY=$SECRET_KEY
REFRESH_SECRET_KEY=$REFRESH_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Stripe — REPLACE WITH YOUR KEYS
STRIPE_SECRET_KEY=sk_test_REPLACE_ME
STRIPE_PUBLISHABLE_KEY=pk_test_REPLACE_ME
STRIPE_WEBHOOK_SECRET=whsec_REPLACE_ME

# OpenAI — REPLACE WITH YOUR KEY
OPENAI_API_KEY=sk-REPLACE_ME

# Monitoring
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASS
TELEGRAM_BOT_TOKEN=REPLACE_ME
TELEGRAM_CHAT_ID=REPLACE_ME

# App
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=info
ENVEOF
    ok ".env created with auto-generated secrets"
    warn "Edit .env to add: STRIPE_SECRET_KEY, OPENAI_API_KEY"
else
    # Update domain-related vars
    sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" .env
    sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://api.$DOMAIN|" .env
    grep -q "^ACME_EMAIL=" .env || echo "ACME_EMAIL=admin@$DOMAIN" >> .env
    ok ".env already exists, domain vars updated"
fi

# ── STEP 7: Check DNS ────────────────────────────────────────
echo "[7/9] Checking DNS..."
RESOLVED=$(dig +short $DOMAIN @8.8.8.8 2>/dev/null | tail -1)
MY_IP=$(curl -s https://api.ipify.org 2>/dev/null || echo "unknown")
if [ "$RESOLVED" = "$MY_IP" ]; then
    ok "DNS: $DOMAIN → $MY_IP ✓"
    DNS_OK=true
else
    warn "DNS not pointing here yet (domain: $RESOLVED, this server: $MY_IP)"
    warn "Add A records in OVH: $DOMAIN + www/api/app/admin/monitor → $MY_IP"
    DNS_OK=false
fi

# ── STEP 8: Build + launch containers ───────────────────────
echo "[8/9] Building and launching containers..."
cd $APP_DIR
docker compose -f infra/docker-compose.prod.yml --env-file .env pull 2>&1 | grep -E "Pull|pull|error" | head -5 || true
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --build 2>&1 | tail -15
sleep 12

RUNNING=$(docker ps --format "{{.Names}}" | wc -l)
ok "$RUNNING containers running"

# ── STEP 9: Final status ─────────────────────────────────────
echo ""
echo "[9/9] ══ FINAL STATUS ══════════════════════════════"
echo ""

# Services
for svc in ufw fail2ban docker; do
    STATUS=$(systemctl is-active $svc 2>/dev/null)
    [ "$STATUS" = "active" ] && ok "$svc" || warn "$svc: $STATUS"
done

echo ""
# Containers
docker ps --format "  {{.Names}}: {{.Status}}" 2>/dev/null

echo ""
echo "  Server IP:   $MY_IP"
echo "  DNS status:  $([ "$DNS_OK" = true ] && echo '✓ Ready' || echo '⚠ Add A records in OVH')"
echo "  .env:        $(grep 'STRIPE_SECRET_KEY' .env | grep -v REPLACE && echo 'configured' || echo '⚠ STRIPE_SECRET_KEY needs real value')"
echo ""

if [ "$DNS_OK" = true ]; then
    echo "══ LIVE ═════════════════════════════════════════"
    echo "  https://$DOMAIN           → Landing"
    echo "  https://api.$DOMAIN       → API + Swagger"
    echo "  https://admin.$DOMAIN     → Admin"
    echo "  https://monitor.$DOMAIN   → Grafana"
    echo ""
    echo "  Grafana: admin / $(grep GRAFANA_ADMIN_PASSWORD .env | cut -d= -f2)"
    echo "  SSH: ssh -i ~/.ssh/id_ed25519 root@$MY_IP"
else
    echo "══ TODO ════════════════════════════════════════"
    echo "  1. OVH Manager → Zone DNS → add 6 A records:"
    echo "     $DOMAIN, www, api, app, admin, monitor → $MY_IP"
    echo "  2. Edit .env: add real STRIPE_SECRET_KEY + OPENAI_API_KEY"
    echo "  3. Re-run: bash $APP_DIR/infra/scripts/fresh-install.sh"
fi
echo ""