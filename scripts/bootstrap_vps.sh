#!/usr/bin/env bash
# Nanovia OS — VPS Bootstrap
# Usage: bash scripts/bootstrap_vps.sh
# Run as root on fresh Ubuntu 22.04 / Debian 12 VPS
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/nanovia}"
: "${REPO_URL:?Set REPO_URL to the Nanovia Git repository URL before running this script}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-nanovia-prod}"
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/nanovia}"
BACKUP_SCHEDULE="${BACKUP_SCHEDULE:-35 3 * * *}"

echo ">>> [1/7] System update"
apt-get update -qq && apt-get upgrade -y -qq

echo ">>> [2/7] Install Docker"
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

echo ">>> [3/8] Install tools"
apt-get install -y -qq git curl ufw fail2ban unzip unattended-upgrades apt-listchanges

echo ">>> [4/8] Firewall (UFW)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment "SSH"
ufw allow 80/tcp   comment "HTTP"
ufw allow 443/tcp  comment "HTTPS"
ufw --force enable

echo ">>> [5/8] Fail2ban"
systemctl enable --now fail2ban

echo ">>> [6/8] Automatic security updates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
EOF

cat > /etc/apt/apt.conf.d/50unattended-upgrades <<'EOF'
Unattended-Upgrade::Origins-Pattern {
        "origin=${distro_id},codename=${distro_codename},label=${distro_id}";
        "origin=${distro_id},codename=${distro_codename},label=${distro_id}-Security";
        "origin=${distro_id},codename=${distro_codename}-security,label=${distro_id}-Security";
};

Unattended-Upgrade::Package-Blacklist {
};

Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:30";
Unattended-Upgrade::SyslogEnable "true";
EOF

systemctl enable --now unattended-upgrades

echo ">>> [7/8] Clone repo"
mkdir -p "$DEPLOY_PATH"
if [ -d "$DEPLOY_PATH/.git" ]; then
  git -C "$DEPLOY_PATH" pull --ff-only
else
  git clone "$REPO_URL" "$DEPLOY_PATH"
fi
mkdir -p "$DEPLOY_PATH/backups"

echo ">>> [8/8] Copy .env"
if [ ! -f "$DEPLOY_PATH/.env" ]; then
  cp "$DEPLOY_PATH/.env.example" "$DEPLOY_PATH/.env"
  echo "⚠️  EDIT $DEPLOY_PATH/.env with real values before starting"
else
  echo ".env already exists — skipping"
fi

echo ">>> [9/9] Automatic backups"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
cat > /etc/cron.d/nanovia-backup <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
DEPLOY_PATH=${DEPLOY_PATH}
COMPOSE_PROJECT=${COMPOSE_PROJECT}
BACKUP_DIR=${BACKUP_DIR}
${BACKUP_SCHEDULE} root cd ${DEPLOY_PATH} && /bin/bash infra/scripts/backup.sh backup >> /var/log/nanovia-backup-cron.log 2>&1
EOF
chmod 644 /etc/cron.d/nanovia-backup
systemctl enable --now cron 2>/dev/null || systemctl enable --now crond 2>/dev/null || true

echo ""
echo "✅ Bootstrap complete."
echo "Next: edit $DEPLOY_PATH/.env then run:"
echo "  cd $DEPLOY_PATH && docker compose -f infra/docker-compose.prod.yml up -d"
echo ""
echo "Automatic security updates are enabled with unattended-upgrades."
echo "Automatic reboot will happen only when required, at 04:30."
echo "Automatic encrypted backups are scheduled via /etc/cron.d/nanovia-backup."
