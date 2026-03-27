#!/bin/bash
# ============================================================
# KT Monetization OS — VPS Rescue Recovery Script
# Run this INSIDE rescue mode SSH session
# ============================================================
set -e

echo "=== KT OS VPS Recovery ==="
echo "Step 1: Finding data disk..."
lsblk -f

# Mount the actual system disk (usually sda1 or vda1)
DISK=""
for d in /dev/sda1 /dev/vda1 /dev/sdb1; do
  if [ -b "$d" ]; then
    DISK=$d
    break
  fi
done

if [ -z "$DISK" ]; then
  echo "ERROR: Cannot find disk. Run 'lsblk' manually."
  exit 1
fi

echo "Step 2: Mounting $DISK to /mnt..."
mount $DISK /mnt 2>/dev/null || true
mount -t ext4 $DISK /mnt 2>/dev/null || true

echo "Step 3: Verifying KT project on disk..."
ls /mnt/opt/kt-monetization-os/ 2>/dev/null && echo "PROJECT FOUND" || echo "PROJECT NOT FOUND"

echo "Step 4: Resetting root password..."
for fs in proc sys dev dev/pts; do
  mount --bind /$fs /mnt/$fs 2>/dev/null || true
done
echo "root:KT@V3rs3!S3cur3#2026" | chroot /mnt chpasswd
echo "Root password reset OK"

echo "Step 5: Checking SSH keys..."
mkdir -p /mnt/root/.ssh
chmod 700 /mnt/root/.ssh
cat /mnt/root/.ssh/authorized_keys 2>/dev/null | head -1 | cut -c1-40 || echo "No authorized_keys"

echo "Step 6: Docker data check..."
ls /mnt/var/lib/docker/volumes/ 2>/dev/null | head -5 || echo "Check docker volumes manually"

echo ""
echo "=== DONE. NOW:"
echo "1. Go to OVH Manager > VPS > Boot > Hard Disk (normal mode)"
echo "2. Click Restart VPS"
echo "3. Wait 2 min then SSH: ssh -i ~/.ssh/id_rsa root@167.114.155.166"
