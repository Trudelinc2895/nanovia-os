#!/bin/bash
# KT SSH Key Recovery — adds ed25519 key to root authorized_keys
# Type this URL in KVM: curl -fsSL https://raw.githubusercontent.com/Trudelinc2895/nanovia-os/main/infra/scripts/add-key.sh | bash
set -e
PUB="${ED25519_PUBKEY:-${1:-}}"

if [ -z "$PUB" ]; then
  echo "Usage: ED25519_PUBKEY='<ed25519-public-key>' bash add-key.sh" >&2
  exit 1
fi

mkdir -p /root/.ssh
chmod 700 /root/.ssh
# Remove duplicate if exists
grep -vF "$PUB" /root/.ssh/authorized_keys > /tmp/ak 2>/dev/null || true
mv /tmp/ak /root/.ssh/authorized_keys 2>/dev/null || true
echo "$PUB" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
echo "SSH key added."
cat /root/.ssh/authorized_keys | wc -l
echo "keys in authorized_keys"

