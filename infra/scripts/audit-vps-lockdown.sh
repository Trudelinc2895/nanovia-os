#!/usr/bin/env bash
set -euo pipefail

echo "== Nanovia VPS Lockdown Audit =="
echo

echo "-- sshd_config.d"
grep -HnE "PermitRootLogin|PasswordAuthentication|AllowUsers|PubkeyAuthentication" /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null || true
echo

echo "-- UFW status"
ufw status numbered || true
echo

echo "-- fail2ban"
systemctl is-enabled fail2ban 2>/dev/null || true
systemctl is-active fail2ban 2>/dev/null || true
fail2ban-client status sshd 2>/dev/null || true
echo

echo "-- unattended upgrades"
systemctl is-enabled unattended-upgrades 2>/dev/null || true
systemctl is-active unattended-upgrades 2>/dev/null || true
echo

echo "-- .env permissions"
if [[ -f /opt/nanovia-os/.env ]]; then
  stat -c "%a %U:%G %n" /opt/nanovia-os/.env
else
  echo "/opt/nanovia-os/.env missing"
fi
