#!/bin/bash
# KT SSH Key Recovery — adds ed25519 key to root authorized_keys
# Type this URL in KVM: curl -fsSL https://raw.githubusercontent.com/Trudelinc2895/kt-monetization-os/main/infra/scripts/add-key.sh | bash
set -e
PUB="<ed25519-public-key>C3NzaC1lZDI1NTE5AAAAIEkMjUt0dkkQgMdlkBc9uhcJ60256s6Dgc6vCHHqoec9 kt-vps-2026"
mkdir -p /root/.ssh
chmod 700 /root/.ssh
# Remove duplicate if exists
grep -v "kt-vps-2026" /root/.ssh/authorized_keys > /tmp/ak 2>/dev/null || true
mv /tmp/ak /root/.ssh/authorized_keys 2>/dev/null || true
echo "$PUB" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
echo "SSH key added. Test: ssh -i ~/.ssh/id_ed25519 root@167.114.155.166"
cat /root/.ssh/authorized_keys | wc -l
echo "keys in authorized_keys"