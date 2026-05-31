#!/usr/bin/env bash
# Nanovia OS - Permanent VPS lockdown
# Run as root AFTER fresh-install.sh and AFTER validating the deploy SSH key.
#
# Example:
#   sudo bash infra/scripts/lock-vps-forever.sh \
#     --deploy-user deploy \
#     --app-dir /opt/nanovia-os \
#     --admin-ip 203.0.113.10/32 \
#     --public-key "ssh-ed25519 AAAA... nanovia-deploy"

set -euo pipefail

DEPLOY_USER="deploy"
APP_DIR="/opt/nanovia-os"
ADMIN_IP=""
DEPLOY_PUBKEY=""
SKIP_SSHD_RESTART="false"
LOG="/var/log/nanovia-vps-lock.log"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  sudo bash infra/scripts/lock-vps-forever.sh [options]

Options:
  --deploy-user <name>     SSH-only deployment user (default: deploy)
  --app-dir <path>         Nanovia install path (default: /opt/nanovia-os)
  --admin-ip <cidr>        Restrict SSH to this source CIDR (recommended)
  --public-key <key>       Deploy SSH public key to inject if missing
  --skip-sshd-restart      Validate SSH config but do not restart sshd
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-user) DEPLOY_USER="$2"; shift 2 ;;
    --app-dir) APP_DIR="$2"; shift 2 ;;
    --admin-ip) ADMIN_IP="$2"; shift 2 ;;
    --public-key) DEPLOY_PUBKEY="$2"; shift 2 ;;
    --skip-sshd-restart) SKIP_SSHD_RESTART="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "Must run as root."

install_base_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ufw fail2ban unattended-upgrades apt-listchanges ca-certificates >/dev/null
  systemctl enable fail2ban unattended-upgrades >/dev/null 2>&1 || true
  systemctl restart fail2ban >/dev/null 2>&1 || true
}

ensure_deploy_user() {
  if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
    useradd --system --create-home --shell /bin/bash "$DEPLOY_USER"
    log "Created deploy user: $DEPLOY_USER"
  fi

  local deploy_home ssh_dir auth_keys
  deploy_home="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
  ssh_dir="$deploy_home/.ssh"
  auth_keys="$ssh_dir/authorized_keys"
  mkdir -p "$ssh_dir"
  chmod 700 "$ssh_dir"
  touch "$auth_keys"
  chmod 600 "$auth_keys"
  chown -R "$DEPLOY_USER:$DEPLOY_USER" "$ssh_dir"

  if [[ -n "$DEPLOY_PUBKEY" ]] && ! grep -qF "$DEPLOY_PUBKEY" "$auth_keys"; then
    echo "$DEPLOY_PUBKEY" >> "$auth_keys"
    chown "$DEPLOY_USER:$DEPLOY_USER" "$auth_keys"
    log "Injected deploy SSH key."
  fi
}

lock_file_permissions() {
  if [[ -d "$APP_DIR" ]]; then
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
  fi

  if [[ -f "$APP_DIR/.env" ]]; then
    chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    log "Locked .env permissions."
  fi

  if getent group docker >/dev/null 2>&1; then
    gpasswd -d "$DEPLOY_USER" docker >/dev/null 2>&1 || true
  fi
}

configure_ufw() {
  ufw --force reset >/dev/null
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  if [[ -n "$ADMIN_IP" ]]; then
    ufw allow from "$ADMIN_IP" to any port 22 proto tcp comment 'Nanovia admin SSH' >/dev/null
  else
    ufw allow 22/tcp comment 'Nanovia admin SSH' >/dev/null
  fi
  ufw allow 80/tcp comment 'Nanovia HTTP' >/dev/null
  ufw allow 443/tcp comment 'Nanovia HTTPS' >/dev/null
  ufw --force enable >/dev/null
  log "UFW locked. SSH source: ${ADMIN_IP:-anywhere}"
}

configure_fail2ban() {
  cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime = 24h
findtime = 10m
maxretry = 3
backend = systemd

[sshd]
enabled = true
port = ssh
maxretry = 3
bantime = 24h
findtime = 10m
EOF
  systemctl enable fail2ban >/dev/null 2>&1 || true
  systemctl restart fail2ban
}

configure_auto_updates() {
  cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
EOF

  cat > /etc/apt/apt.conf.d/50unattended-upgrades <<'EOF'
Unattended-Upgrade::Origins-Pattern {
        "origin=${distro_id},codename=${distro_codename},label=${distro_id}";
        "origin=${distro_id},codename=${distro_codename}-security,label=${distro_id}-Security";
        "origin=${distro_id},codename=${distro_codename},label=${distro_id}-Security";
};

Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:30";
EOF
  systemctl enable unattended-upgrades >/dev/null 2>&1 || true
  systemctl restart unattended-upgrades >/dev/null 2>&1 || true
}

configure_sysctl() {
  local sysctl_file="/etc/sysctl.d/99-nanovia-lockdown.conf"
  cat > "$sysctl_file" <<'EOF'
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
kernel.dmesg_restrict = 1
EOF
  sysctl --system >/dev/null
}

configure_sshd() {
  mkdir -p /etc/ssh/sshd_config.d
  cat > /etc/ssh/sshd_config.d/99-nanovia-lockdown.conf <<EOF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
AllowUsers $DEPLOY_USER
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
EOF

  sshd -t || die "sshd validation failed."
  if [[ "$SKIP_SSHD_RESTART" == "true" ]]; then
    log "sshd validated but not restarted (--skip-sshd-restart)."
  else
    systemctl restart sshd
    log "sshd restarted with deploy-only access."
  fi
}

main() {
  log "Starting permanent VPS lockdown."
  install_base_packages
  ensure_deploy_user
  lock_file_permissions
  configure_ufw
  configure_fail2ban
  configure_auto_updates
  configure_sysctl
  configure_sshd
  log "Nanovia VPS lockdown complete."
}

main "$@"
