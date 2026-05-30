#!/usr/bin/env python3
"""Bootstrap VPS — upload script + exec avec tail du log."""
import paramiko, time, sys, os

HOST = '167.114.155.166'
USER = 'root'
KEY_PATH = r'C:\Users\Alienware\.ssh\id_rsa'
ENV_PATH = r'C:\Users\Alienware\nanovia-os\.env'

BOOTSTRAP_SH = r"""#!/bin/bash
set -e
LOG=/tmp/kt_bootstrap.log
exec > >(tee -a $LOG) 2>&1

echo "=============================="
echo " KT BOOTSTRAP START $(date)"
echo "=============================="

# 1. Paquets de base
echo "[1/7] APT update + paquets..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl wget git unzip ufw fail2ban htop ca-certificates gnupg
echo "  OK paquets de base"

# 2. Docker
echo "[2/7] Docker..."
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
  echo "  Docker installe"
else
  echo "  Docker deja present: $(docker --version)"
fi
docker compose version || apt-get install -y docker-compose-plugin

# 3. UFW
echo "[3/7] UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
echo "  UFW actif: 22/80/443"

# 4. fail2ban
echo "[4/7] fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban || true
echo "  fail2ban OK"

# 5. Clone repo
echo "[5/7] Clone repo..."
mkdir -p /opt/nanovia-os
if [ -d "/opt/nanovia-os/.git" ]; then
  cd /opt/nanovia-os && git pull origin main
  echo "  Repo mis a jour"
else
  git clone https://github.com/Trudelinc2895/nanovia-os.git /opt/nanovia-os
  echo "  Repo clone"
fi

# 6. Verifier .env
echo "[6/7] Verification .env..."
if [ -f "/opt/nanovia-os/.env" ]; then
  echo "  .env present OK"
else
  echo "  ATTENTION: .env manquant! Sera copie apres."
fi

# 7. Docker Compose
echo "[7/7] Docker Compose up..."
cd /opt/nanovia-os
docker compose -f infra/docker-compose.prod.yml pull --quiet || true
docker compose -f infra/docker-compose.prod.yml up -d --build
sleep 5
echo ""
echo "=============================="
echo " CONTAINERS:"
docker ps --format 'table {{.Names}}\t{{.Status}}'
echo ""
echo " BOOTSTRAP COMPLETE $(date)"
echo "=============================="
echo "DONE"
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
print(f"=== CONNECTE: {HOST} ===")

# Upload bootstrap.sh
sftp = ssh.open_sftp()
with sftp.open('/tmp/kt_bootstrap.sh', 'w') as f:
    f.write(BOOTSTRAP_SH)

# Upload .env
if os.path.exists(ENV_PATH):
    sftp.put(ENV_PATH, '/opt/nanovia-os/.env')
    print("  .env pre-copie (si dossier existe)")
sftp.close()

# chmod + exec en background avec nohup
_, stdout, _ = ssh.exec_command("chmod +x /tmp/kt_bootstrap.sh && nohup bash /tmp/kt_bootstrap.sh > /tmp/kt_bootstrap.log 2>&1 &")
stdout.read()
print("  Bootstrap lance en background sur VPS")
print("  Suivi du log en live...\n")

# Tail du log en live
time.sleep(3)
channel = ssh.invoke_shell()
channel.send("tail -f /tmp/kt_bootstrap.log\n")
time.sleep(2)

start = time.time()
last_output = ""
while time.time() - start < 600:  # max 10 min
    if channel.recv_ready():
        chunk = channel.recv(4096).decode('utf-8', errors='replace')
        # Nettoyer les escape codes ANSI
        import re
        chunk = re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', chunk)
        chunk = re.sub(r'\r', '', chunk)
        if chunk.strip():
            print(chunk, end='', flush=True)
            last_output += chunk
    if "BOOTSTRAP COMPLETE" in last_output or "DONE" in last_output:
        print("\n\n=== BOOTSTRAP TERMINE ===")
        break
    time.sleep(0.5)

# Copier .env une fois le repo cloné
print("\n[POST] Copie .env finale...")
if os.path.exists(ENV_PATH):
    sftp2 = ssh.open_sftp()
    sftp2.put(ENV_PATH, '/opt/nanovia-os/.env')
    sftp2.close()
    print("  .env copie sur VPS ✅")

# Status final
_, out, _ = ssh.exec_command("docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
result = out.read().decode()
print("\n=== DOCKER STATUS ===")
print(result)

ssh.close()
print("\nDONE. VPS bootstrap complet.")

