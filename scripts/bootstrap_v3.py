#!/usr/bin/env python3
"""Bootstrap VPS v3 — sans SFTP, tout via exec_command + base64."""
import paramiko, time, os, base64, re

HOST = '167.114.155.166'
USER = 'root'
KEY_PATH = r'C:\Users\Alienware\.ssh\id_rsa'
ENV_PATH = r'C:\Users\Alienware\nanovia-os\.env'

def clean(text):
    return re.sub(r'\x1b\[[0-9;]*[mGKHF]|\r', '', text)

def run(ssh, cmd, timeout=180):
    chan = ssh.get_transport().open_session()
    chan.set_combine_stderr(True)
    chan.exec_command(cmd)
    out = b''
    while True:
        if chan.recv_ready():
            out += chan.recv(8192)
        elif chan.exit_status_ready():
            while chan.recv_ready():
                out += chan.recv(8192)
            break
        else:
            time.sleep(0.3)
    rc = chan.recv_exit_status()
    return rc, clean(out.decode('utf-8', errors='replace'))

def upload_b64(ssh, local_path, remote_path):
    """Upload fichier via base64 encode/decode."""
    with open(local_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode()
    # Split en chunks de 2000 chars pour éviter les limites
    chunks = [content[i:i+2000] for i in range(0, len(content), 2000)]
    # Écrire premier chunk
    run(ssh, f"echo '{chunks[0]}' > /tmp/_b64_upload")
    # Appender les suivants
    for chunk in chunks[1:]:
        run(ssh, f"echo '{chunk}' >> /tmp/_b64_upload")
    run(ssh, f"base64 -d /tmp/_b64_upload > {remote_path} && rm /tmp/_b64_upload")

def upload_text(ssh, content, remote_path):
    """Upload texte via base64."""
    encoded = base64.b64encode(content.encode('utf-8')).decode()
    chunks = [encoded[i:i+2000] for i in range(0, len(encoded), 2000)]
    run(ssh, f"echo '{chunks[0]}' > /tmp/_b64_upload")
    for chunk in chunks[1:]:
        run(ssh, f"echo '{chunk}' >> /tmp/_b64_upload")
    run(ssh, f"base64 -d /tmp/_b64_upload > {remote_path} && rm /tmp/_b64_upload")

BOOTSTRAP_SH = """#!/bin/bash
set -e
LOG=/tmp/kt_bootstrap.log
exec > >(tee -a $LOG) 2>&1

echo "=============================="
echo " KT BOOTSTRAP START $(date)"
echo "=============================="

export DEBIAN_FRONTEND=noninteractive

echo "[1/6] APT update + paquets..."
apt-get update -qq 2>&1 | tail -3
apt-get install -y -qq curl wget git unzip ca-certificates gnupg fail2ban htop 2>&1 | tail -3
echo "  paquets OK"

echo "[2/6] Docker..."
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh 2>&1 | tail -5
  systemctl enable docker && systemctl start docker
else
  echo "  deja installe: $(docker --version)"
fi
apt-get install -y -qq docker-compose-plugin 2>&1 | tail -2
echo "  docker compose: $(docker compose version)"

echo "[3/6] fail2ban..."
systemctl enable fail2ban && systemctl start fail2ban || true
echo "  fail2ban OK"

echo "[4/6] Clone repo..."
mkdir -p /opt/nanovia-os
if [ -d "/opt/nanovia-os/.git" ]; then
  cd /opt/nanovia-os && git pull origin main 2>&1
else
  git clone https://github.com/Trudelinc2895/nanovia-os.git /opt/nanovia-os 2>&1
fi
echo "  repo OK: $(ls /opt/nanovia-os | tr '\\n' ' ')"

echo "[5/6] Verification .env..."
[ -f /opt/nanovia-os/.env ] && echo "  .env OK" || echo "  MANQUANT"

echo "[6/6] Docker Compose..."
cd /opt/nanovia-os
docker compose -f infra/docker-compose.prod.yml up -d --build 2>&1 | tail -20
sleep 5
echo ""
echo "=============================="
echo " CONTAINERS:"
docker ps --format 'table {{.Names}}\\t{{.Status}}'
echo " DONE $(date)"
echo "=============================="
"""

# ── CONNEXION ───────────────────────────────────────
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
print(f"=== CONNECTE: {HOST} ===\n")

# ── STEP 0: Fixer sshd_config (ajouter Subsystem sftp) ───
print("[0/7] Fix sshd_config (ajouter SFTP subsystem)...")
SSHD = """# KT Secured SSH Config
Port 22
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
PermitEmptyPasswords no
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
Subsystem sftp /usr/lib/openssh/sftp-server
"""
upload_text(ssh, SSHD, '/etc/ssh/sshd_config')
rc, out = run(ssh, 'sshd -t && systemctl reload sshd && echo SSHD_OK')
print(f"  {out.strip()}")

# ── STEP 1: Upload .env ───────────────────────────────
print("\n[1/7] Upload .env...")
run(ssh, 'mkdir -p /opt/nanovia-os')
if os.path.exists(ENV_PATH):
    upload_b64(ssh, ENV_PATH, '/opt/nanovia-os/.env')
    rc, out = run(ssh, 'wc -l /opt/nanovia-os/.env')
    print(f"  .env copie: {out.strip()} lignes ✅")
else:
    print("  ERREUR: .env introuvable localement!")

# ── STEP 2: Upload + run bootstrap.sh ────────────────
print("\n[2/7] Upload bootstrap.sh...")
upload_text(ssh, BOOTSTRAP_SH, '/tmp/kt_bootstrap.sh')
run(ssh, 'chmod +x /tmp/kt_bootstrap.sh')
print("  bootstrap.sh uploade ✅")

print("\n[3/7] Lancement bootstrap (peut prendre 3-5 min)...")
run(ssh, 'nohup bash /tmp/kt_bootstrap.sh > /tmp/kt_bootstrap.log 2>&1 &')
print("  bootstrap lance en background ✅")

# ── Suivi live du log ─────────────────────────────────
print("\n[LIVE LOG] Suivi installation...\n")
time.sleep(5)

last_pos = 0
done = False
for i in range(120):  # max 10 min
    rc, out = run(ssh, f'tail -c +{last_pos+1} /tmp/kt_bootstrap.log 2>/dev/null || echo ""')
    if out.strip():
        print(out, end='', flush=True)
        last_pos += len(out.encode('utf-8'))
    if 'DONE' in out or 'BOOTSTRAP COMPLETE' in out or 'DONE' in out:
        done = True
        break
    # Vérifier si le process est encore en cours
    rc2, running = run(ssh, "pgrep -f kt_bootstrap.sh || echo FINISHED")
    if 'FINISHED' in running and i > 5:
        # Lire le reste du log
        rc3, final = run(ssh, 'cat /tmp/kt_bootstrap.log 2>/dev/null || echo ""')
        if final.strip() and final != out:
            print(final[-2000:])
        done = True
        break
    time.sleep(5)

if not done:
    rc, final_log = run(ssh, 'tail -50 /tmp/kt_bootstrap.log')
    print(final_log)

# ── Status final ──────────────────────────────────────
print("\n\n=== STATUS FINAL ===")
rc, out = run(ssh, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo 'Docker pas encore pret'")
print(out)

rc2, out2 = run(ssh, 'curl -s http://localhost:8010/health 2>/dev/null || echo "API pas encore prête"')
print(f"\nAPI health: {out2}")

ssh.close()
print("\n=== BOOTSTRAP COMPLET ===")

