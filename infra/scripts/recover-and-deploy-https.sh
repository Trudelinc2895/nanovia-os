#!/bin/bash
# ============================================================
# Nanovia OS — Recovery + HTTPS Deploy Script v3
# Run ONCE after VPS recovery to restore everything
# Usage: bash /opt/kt-monetization-os/infra/scripts/recover-and-deploy-https.sh
# ============================================================
set -e
DOMAIN="nanovia.ca"
APP_DIR="/opt/kt-monetization-os"
ED25519_KEY="${ED25519_PUBKEY:-}"

echo "══════════════════════════════════════════"
echo "  Nanovia Recovery + HTTPS Deploy v3"
echo "══════════════════════════════════════════"

# ── STEP 1: Kill nftables permanently ───────────────────────
echo "[1/9] Removing nftables..."
systemctl stop nftables 2>/dev/null || true
systemctl disable nftables 2>/dev/null || true
nft flush ruleset 2>/dev/null || true
apt-get remove -y nftables 2>/dev/null | tail -1 || true
echo "  OK nftables removed permanently"

# ── STEP 2: Restore UFW + iptables ──────────────────────────
echo "[2/9] Restoring firewall..."
iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT
ufw --force enable
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 8020/tcp
ufw deny 9091/tcp
ufw reload
echo "  OK UFW restored — SSH/HTTP/HTTPS open"

# ── STEP 3: Add SSH key for passwordless access ──────────────
echo "[3/9] Adding ed25519 SSH key..."
if [ -n "$ED25519_KEY" ]; then
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    grep -vF "$ED25519_KEY" /root/.ssh/authorized_keys > /tmp/ak 2>/dev/null || true
    mv /tmp/ak /root/.ssh/authorized_keys 2>/dev/null || true
    echo "$ED25519_KEY" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    echo "  OK ed25519 key added ($(wc -l < /root/.ssh/authorized_keys) keys total)"
else
    echo "  SKIP no ED25519_PUBKEY provided"
fi

# ── STEP 4: Restore security services ───────────────────────
echo "[4/9] Restarting security services..."
for svc in fail2ban crowdsec kt-spy-agent kt-watchdog; do
    systemctl start $svc 2>/dev/null && echo "  OK $svc" || echo "  SKIP $svc"
done

# ── STEP 5: Fix .env for domain-based URLs ──────────────────
echo "[5/9] Updating .env for https://$DOMAIN..."
cd $APP_DIR

for key in \
    "API_BASE_URL=https://$DOMAIN" \
    "NEXT_PUBLIC_API_URL=" \
    "PUBLIC_WEB_URL=https://$DOMAIN" \
    "PRIVATE_ADMIN_URL=" \
    "DOMAIN=$DOMAIN" \
    "ACME_EMAIL=admin@$DOMAIN"; do
    k="${key%%=*}"
    sed -i "/^$k=/d" .env
    echo "$key" >> .env
done

if grep -q "^ALLOWED_ORIGINS_RAW=" .env; then
    sed -i "s|^ALLOWED_ORIGINS_RAW=.*|ALLOWED_ORIGINS_RAW=https://$DOMAIN|g" .env
else
    echo "ALLOWED_ORIGINS_RAW=https://$DOMAIN" >> .env
fi

# Add monitoring env vars if not present
for var in "TELEGRAM_BOT_TOKEN=" "TELEGRAM_CHAT_ID=" "GRAFANA_ADMIN_USER=admin" "GRAFANA_ADMIN_PASSWORD="; do
    k="${var%%=*}"
    grep -q "^$k=" .env || echo "$var" >> .env
done

echo "  OK .env updated"

# ── STEP 6: Pull latest code ─────────────────────────────────
echo "[6/9] Pulling latest code from GitHub..."
cd $APP_DIR
git pull origin main 2>&1 | tail -3
chmod +x infra/scripts/*.sh 2>/dev/null || true
echo "  OK Code updated ($(git rev-parse --short HEAD))"

# ── STEP 7: Check DNS ────────────────────────────────────────
echo "[7/9] Checking DNS for $DOMAIN..."
apt-get install -y dnsutils 2>/dev/null | tail -1 || true
RESOLVED=$(dig +short $DOMAIN @8.8.8.8 2>/dev/null | tail -1)
if [ "$RESOLVED" = "167.114.155.166" ]; then
    echo "  OK DNS: $DOMAIN -> $RESOLVED"
    DNS_OK=true
else
    echo "  WARN DNS not ready ($RESOLVED) — add A records in OVH Manager"
    DNS_OK=false
fi

# ── STEP 8: Rebuild + restart all containers ────────────────
echo "[8/9] Rebuilding and restarting containers..."
cd $APP_DIR
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --remove-orphans 2>&1 | tail -10
sleep 10
echo "  OK Containers started"

# ── STEP 9: Final status ─────────────────────────────────────
echo "[9/9] Final status..."
echo ""
for svc in ufw fail2ban crowdsec kt-spy-agent kt-watchdog; do
    STATUS=$(systemctl is-active $svc 2>/dev/null || echo "inactive")
    [ "$STATUS" = "active" ] && echo "  OK $svc" || echo "  INFO $svc → $STATUS"
done
echo ""
docker ps --format "  {{.Names}} | {{.Status}}" 2>/dev/null
echo ""
echo "  SSH key: $(wc -l < /root/.ssh/authorized_keys) keys in authorized_keys"
echo "  NEXT_PUBLIC_API_URL=$(grep NEXT_PUBLIC_API_URL .env | cut -d= -f2)"
echo "  DOMAIN=$(grep '^DOMAIN=' .env | cut -d= -f2)"
echo ""
if [ "$DNS_OK" = true ]; then
    echo "══ LIVE ══════════════════════════════════"
    echo "  https://$DOMAIN"
    echo "  https://$DOMAIN/api/v1"
    echo "  SSH: use your configured deploy key"
else
    echo "══ ADD DNS A RECORDS IN OVH MANAGER ═════"
    echo "  nanovia.ca         -> 167.114.155.166"
    echo "  (optional) www.nanovia.ca     -> 167.114.155.166"
    echo "  (optional) admin.nanovia.ca   -> 167.114.155.166"
    echo "  (optional) monitor.nanovia.ca -> 167.114.155.166"
fi
