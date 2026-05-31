#!/usr/bin/env bash
# setup-deploy-user.sh — Run ONCE as root on the VPS, AFTER fresh-install.sh
# Creates an unprivileged 'deploy' user with Docker access and SSH key auth.
# Hardens sshd: disables root login and password auth.
#
# Usage: sudo bash infra/scripts/setup-deploy-user.sh <deploy_ssh_public_key>
#
# Example:
#   sudo bash infra/scripts/setup-deploy-user.sh \
#     "<ed25519-public-key> github-actions-deploy"
#
# RISK: This script restarts sshd at the end.
# Verify that the deploy key works in a second terminal before exiting root session.

set -euo pipefail

APP_DIR="/opt/nanovia-os"
DEPLOY_USER="deploy"
LOG="/var/log/setup-deploy-user.log"

log() { echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $*" | tee -a "$LOG"; }
die() { log "ERROR: $*"; exit 1; }

[[ $EUID -eq 0 ]] || die "Must run as root"
[[ $# -ge 1 ]] || die "Usage: $0 <deploy_ssh_public_key>"

DEPLOY_PUBKEY="$1"

# ── 1. Create deploy user ──────────────────────────────────────────────────────
if id "$DEPLOY_USER" &>/dev/null; then
  log "User '$DEPLOY_USER' already exists — skipping creation"
else
  useradd --system --create-home --shell /bin/bash "$DEPLOY_USER"
  log "Created user '$DEPLOY_USER'"
fi

# ── 2. Add to docker group (allows docker compose without sudo) ────────────────
if getent group docker &>/dev/null; then
  usermod -aG docker "$DEPLOY_USER"
  log "Added '$DEPLOY_USER' to 'docker' group"
else
  die "'docker' group does not exist — is Docker installed? Run fresh-install.sh first."
fi

# ── 3. SSH key setup ──────────────────────────────────────────────────────────
DEPLOY_HOME=$(getent passwd "$DEPLOY_USER" | cut -d: -f6)
SSH_DIR="$DEPLOY_HOME/.ssh"
AUTH_KEYS="$SSH_DIR/authorized_keys"

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
chown "$DEPLOY_USER:$DEPLOY_USER" "$SSH_DIR"

# Append key only if not already present
if grep -qF "$DEPLOY_PUBKEY" "$AUTH_KEYS" 2>/dev/null; then
  log "SSH public key already in authorized_keys — skipping"
else
  echo "$DEPLOY_PUBKEY" >> "$AUTH_KEYS"
  log "Added SSH public key to $AUTH_KEYS"
fi

chmod 600 "$AUTH_KEYS"
chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH_KEYS"

# ── 4. App directory ownership ────────────────────────────────────────────────
if [[ -d "$APP_DIR" ]]; then
  chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
  log "Transferred ownership of $APP_DIR to '$DEPLOY_USER'"
else
  log "WARNING: $APP_DIR does not exist — ownership not set (will be set on first deploy)"
fi

# ── 5. Backup cron ────────────────────────────────────────────────────────────
CRON_FILE="/etc/cron.d/nanovia-backup"
if [[ -f "$CRON_FILE" ]]; then
  log "Cron job $CRON_FILE already exists — skipping"
else
  cat > "$CRON_FILE" <<'CRON'
# Nanovia OS — daily backup at 03:00 UTC
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 3 * * * deploy bash /opt/nanovia-os/infra/scripts/backup.sh >> /var/log/nanovia-backup.log 2>&1
CRON
  chmod 644 "$CRON_FILE"
  log "Created backup cron: $CRON_FILE"
fi

# ── 6. Logrotate for Caddy and backup logs ────────────────────────────────────
LOGROTATE_FILE="/etc/logrotate.d/kt-monetization"
if [[ -f "$LOGROTATE_FILE" ]]; then
  log "Logrotate config already exists — skipping"
else
  cat > "$LOGROTATE_FILE" <<'LOGROTATE'
/var/log/caddy/*.log /var/log/nanovia-backup.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root adm
    sharedscripts
    postrotate
        # Caddy reopens log files on SIGUSR1 (no reload needed)
        pkill -USR1 caddy 2>/dev/null || true
    endscript
}
LOGROTATE
  chmod 644 "$LOGROTATE_FILE"
  log "Created logrotate config: $LOGROTATE_FILE"
fi

# ── 7. SSH hardening — sshd_config ────────────────────────────────────────────
# CRITICAL: Back up config before modifying. sshd restart is the LAST step.
SSHD_CONFIG="/etc/ssh/sshd_config"
SSHD_BACKUP="/etc/ssh/sshd_config.bak.$(date +%Y%m%d%H%M%S)"

cp "$SSHD_CONFIG" "$SSHD_BACKUP"
log "Backed up sshd_config to $SSHD_BACKUP"

# Apply hardening — use sed to modify existing directives or append if absent
apply_sshd_setting() {
  local key="$1"
  local value="$2"
  if grep -qE "^#?${key}\s" "$SSHD_CONFIG"; then
    sed -i "s|^#\?${key}\s.*|${key} ${value}|" "$SSHD_CONFIG"
  else
    echo "${key} ${value}" >> "$SSHD_CONFIG"
  fi
  log "sshd: set ${key}=${value}"
}

apply_sshd_setting "PermitRootLogin"          "no"
apply_sshd_setting "PasswordAuthentication"   "no"
apply_sshd_setting "ChallengeResponseAuthentication" "no"
apply_sshd_setting "PubkeyAuthentication"     "yes"
apply_sshd_setting "AuthorizedKeysFile"       ".ssh/authorized_keys"
apply_sshd_setting "MaxAuthTries"             "3"
apply_sshd_setting "ClientAliveInterval"      "300"
apply_sshd_setting "ClientAliveCountMax"      "2"
apply_sshd_setting "LoginGraceTime"           "30"
apply_sshd_setting "X11Forwarding"            "no"
apply_sshd_setting "AllowAgentForwarding"     "no"
apply_sshd_setting "AllowTcpForwarding"       "no"

# AllowUsers — allow both root (temporarily) and deploy
# Once deploy access is confirmed, remove root from AllowUsers manually.
if grep -qE "^AllowUsers" "$SSHD_CONFIG"; then
  log "AllowUsers already set — not overwriting (verify it includes '$DEPLOY_USER')"
else
  echo "AllowUsers root $DEPLOY_USER" >> "$SSHD_CONFIG"
  log "sshd: set AllowUsers=root $DEPLOY_USER (remove root after verifying deploy access)"
fi

# Validate config before restarting
sshd -t -f "$SSHD_CONFIG" || die "sshd config validation failed — NOT restarting. Restore: cp $SSHD_BACKUP $SSHD_CONFIG"

log "sshd config valid — restarting sshd"

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTANT: From this point root SSH login with password is disabled.
# Make sure you have a working deploy SSH key in a separate terminal before running this.
# ─────────────────────────────────────────────────────────────────────────────
systemctl restart sshd

log "Done. NEXT STEPS:"
log "  1. In a new terminal: ssh deploy@<VPS_IP> — confirm access"
log "  2. Run: sudo bash $APP_DIR/infra/scripts/lock-vps-forever.sh --deploy-user $DEPLOY_USER --admin-ip <YOUR_IP/32>"
log "  3. Run: sudo bash $APP_DIR/infra/scripts/audit-vps-lockdown.sh"
log "  4. Confirm GitHub Actions deploy succeeds with VPS_SSH_PRIVATE_KEY"
