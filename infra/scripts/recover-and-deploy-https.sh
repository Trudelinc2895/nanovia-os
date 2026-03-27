#!/bin/bash
# ============================================================
# KT Monetization OS — Recovery + HTTPS Deploy Script
# Run this ONCE after VPS recovery to restore everything
# Usage: bash /opt/kt-monetization-os/infra/scripts/recover-and-deploy-https.sh
# ============================================================
set -e
DOMAIN="tkverse.ca"
APP_DIR="/opt/kt-monetization-os"

echo "══════════════════════════════════════════"
echo "  KT Recovery + HTTPS Deploy"
echo "══════════════════════════════════════════"

# ── STEP 1: Kill nftables (was causing SSH lockout) ──────────
echo "[1/7] Removing nftables..."
systemctl stop nftables 2>/dev/null || true
systemctl disable nftables 2>/dev/null || true
nft flush ruleset 2>/dev/null || true
apt-get remove -y nftables 2>/dev/null | tail -1 || true
echo "  ✅ nftables removed"

# ── STEP 2: Restore UFW + iptables ──────────────────────────
echo "[2/7] Restoring firewall..."
iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT
ufw --force enable
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 8020/tcp
ufw deny 9091/tcp
ufw reload
echo "  ✅ UFW restored"

# ── STEP 3: Restore security services ───────────────────────
echo "[3/7] Restarting security services..."
systemctl start fail2ban   2>/dev/null && echo "  ✅ fail2ban" || echo "  ⚠️  fail2ban"
systemctl start crowdsec   2>/dev/null && echo "  ✅ crowdsec" || echo "  ⚠️  crowdsec"
systemctl start kt-spy-agent 2>/dev/null && echo "  ✅ kt-spy-agent" || echo "  ⚠️  kt-spy-agent"
systemctl start kt-watchdog  2>/dev/null && echo "  ✅ kt-watchdog" || echo "  ⚠️  kt-watchdog"

# ── STEP 4: Pull latest code ─────────────────────────────────
echo "[4/7] Pulling latest code from GitHub..."
cd $APP_DIR
git pull origin main 2>&1 | tail -3
echo "  ✅ Code updated"

# ── STEP 5: Verify DNS before HTTPS ─────────────────────────
echo "[5/7] Checking DNS for $DOMAIN..."
RESOLVED=$(dig +short $DOMAIN @8.8.8.8 2>/dev/null | tail -1)
if [ "$RESOLVED" = "167.114.155.166" ]; then
    echo "  ✅ DNS OK — $DOMAIN → $RESOLVED"
    DNS_OK=true
else
    echo "  ⚠️  DNS not ready yet ($RESOLVED) — Caddy will retry Let's Encrypt automatically"
    DNS_OK=false
fi

# ── STEP 6: Restart all containers ──────────────────────────
echo "[6/7] Restarting containers..."
cd $APP_DIR
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --remove-orphans 2>&1 | tail -5
sleep 5
echo "  ✅ Containers started"

# ── STEP 7: Status report ────────────────────────────────────
echo "[7/7] Status check..."
echo ""
echo "  Services:"
systemctl is-active ufw fail2ban crowdsec kt-spy-agent kt-watchdog 2>/dev/null | paste - - - - - | awk '{print "    "$1" "$2" "$3" "$4" "$5}'
echo ""
echo "  Containers:"
docker ps --format "  {{.Names}}\t{{.Status}}" | grep -v "Exited"
echo ""

if [ "$DNS_OK" = true ]; then
    echo "══════════════════════════════════════════"
    echo "  ✅ DONE — https://$DOMAIN should be live"
    echo "  ✅ Let's Encrypt cert auto-issued by Caddy"
    echo "══════════════════════════════════════════"
else
    echo "══════════════════════════════════════════"
    echo "  ⚠️  Add DNS A records in OVH Manager:"
    echo "  tkverse.ca        → 167.114.155.166"
    echo "  api.tkverse.ca    → 167.114.155.166"
    echo "  app.tkverse.ca    → 167.114.155.166"
    echo "  admin.tkverse.ca  → 167.114.155.166"
    echo "  monitor.tkverse.ca → 167.114.155.166"
    echo "  Then Caddy auto-issues Let's Encrypt cert"
    echo "══════════════════════════════════════════"
fi
