#!/usr/bin/env bash
# Nanovia OS — VPS Bootstrap
# Usage: bash scripts/bootstrap_vps.sh
# Run as root on fresh Ubuntu 22.04 / Debian 12 VPS
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/nanovia}"
: "${REPO_URL:?Set REPO_URL to the Nanovia Git repository URL before running this script}"

echo ">>> [1/7] System update"
apt-get update -qq && apt-get upgrade -y -qq

echo ">>> [2/7] Install Docker"
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

echo ">>> [3/7] Install tools"
apt-get install -y -qq git curl ufw fail2ban unzip

echo ">>> [4/7] Firewall (UFW)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment "SSH"
ufw allow 80/tcp   comment "HTTP"
ufw allow 443/tcp  comment "HTTPS"
ufw --force enable

echo ">>> [5/7] Fail2ban"
systemctl enable --now fail2ban

echo ">>> [6/7] Clone repo"
mkdir -p "$DEPLOY_PATH"
if [ -d "$DEPLOY_PATH/.git" ]; then
  git -C "$DEPLOY_PATH" pull --ff-only
else
  git clone "$REPO_URL" "$DEPLOY_PATH"
fi
mkdir -p "$DEPLOY_PATH/backups"

echo ">>> [7/7] Copy .env"
if [ ! -f "$DEPLOY_PATH/.env" ]; then
  cp "$DEPLOY_PATH/.env.example" "$DEPLOY_PATH/.env"
  echo "⚠️  EDIT $DEPLOY_PATH/.env with real values before starting"
else
  echo ".env already exists — skipping"
fi

echo ""
echo "✅ Bootstrap complete."
echo "Next: edit $DEPLOY_PATH/.env then run:"
echo "  cd $DEPLOY_PATH && docker compose -f infra/docker-compose.prod.yml up -d"
