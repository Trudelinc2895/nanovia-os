#!/usr/bin/env python3
"""Fix git clone + docker compose up sur VPS."""
import paramiko, time, re, os, base64

HOST = '167.114.155.166'
USER = 'root'
KEY_PATH = r'C:\Users\Alienware\.ssh\id_rsa'
ENV_PATH = r'C:\Users\Alienware\kt-monetization-os\.env'

def run(ssh, cmd, timeout=300, show=True):
    chan = ssh.get_transport().open_session()
    chan.set_combine_stderr(True)
    chan.exec_command(cmd)
    out = b''
    while True:
        if chan.recv_ready():
            chunk = chan.recv(8192)
            out += chunk
            if show:
                print(re.sub(r'\x1b\[[0-9;]*[mGKHF]|\r','',chunk.decode('utf-8','replace')), end='', flush=True)
        elif chan.exit_status_ready():
            while chan.recv_ready():
                out += chan.recv(8192)
            break
        else:
            time.sleep(0.3)
    rc = chan.recv_exit_status()
    return rc, re.sub(r'\x1b\[[0-9;]*[mGKHF]|\r','',out.decode('utf-8','replace'))

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
print(f"=== CONNECTE: {HOST} ===\n")

# Fix SSH service name (Ubuntu 24 = ssh, pas sshd)
print("[0] Fix sshd_config + reload SSH...")
SSHD = """Port 22
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
encoded = base64.b64encode(SSHD.encode()).decode()
run(ssh, f"echo '{encoded}' | base64 -d > /etc/ssh/sshd_config", show=False)
rc, out = run(ssh, "sshd -t && systemctl reload ssh && echo SSH_RELOADED || echo SSH_RELOAD_FAILED", show=False)
print(f"  {out.strip()}")

# Git clone — init dans le dossier existant
print("\n[1] Git clone (dossier existant — git init + pull)...")
cmds = [
    "cp /opt/kt-monetization-os/.env /tmp/.env.backup 2>/dev/null || true",
    "cd /opt/kt-monetization-os && git init",
    "cd /opt/kt-monetization-os && git remote add origin https://github.com/Trudelinc2895/kt-monetization-os.git 2>/dev/null || git remote set-url origin https://github.com/Trudelinc2895/kt-monetization-os.git",
    "cd /opt/kt-monetization-os && git fetch origin main",
    "cd /opt/kt-monetization-os && git reset --hard origin/main",
    "cp /tmp/.env.backup /opt/kt-monetization-os/.env 2>/dev/null || true",
]
for cmd in cmds:
    rc, out = run(ssh, cmd, show=False)
    label = cmd.split('&&')[-1].strip()[:60]
    status = "✅" if rc == 0 else "⚠️"
    print(f"  {status} {label}")

rc, out = run(ssh, "ls /opt/kt-monetization-os/", show=False)
print(f"  Contenu: {out.strip()[:120]}")

# Vérifier .env
print("\n[2] Vérification .env...")
rc, out = run(ssh, "wc -l /opt/kt-monetization-os/.env && head -3 /opt/kt-monetization-os/.env", show=False)
print(f"  {out.strip()}")

# SSH service fix
print("\n[3] Fix SSH service (Ubuntu 24 = 'ssh' pas 'sshd')...")
rc, out = run(ssh, "systemctl status ssh --no-pager -l | head -5", show=False)
print(f"  {out.strip()[:200]}")

# Docker Compose up
print("\n[4] Docker Compose up (peut prendre 3-5 min)...")
print("  Pull images...\n")
rc, out = run(ssh, "cd /opt/kt-monetization-os && docker compose -f infra/docker-compose.prod.yml pull 2>&1", timeout=600)
print("\n  Build + up...\n")
rc2, out2 = run(ssh, "cd /opt/kt-monetization-os && docker compose -f infra/docker-compose.prod.yml up -d --build 2>&1", timeout=600)

# Status containers
print("\n\n=== DOCKER STATUS ===")
rc3, out3 = run(ssh, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", show=False)
print(out3)

# Test API health
print("\n[5] Test API health...")
time.sleep(8)
rc4, out4 = run(ssh, "curl -s http://localhost:8010/health 2>/dev/null || echo 'API pas encore prête'", show=False)
print(f"  GET /health → {out4.strip()}")

rc5, out5 = run(ssh, "curl -s http://localhost:8010/ 2>/dev/null || echo 'Root pas encore prêt'", show=False)
print(f"  GET / → {out5.strip()[:100]}")

print("\n=== RÉSUMÉ VPS ===")
rc6, out6 = run(ssh, "docker ps --format '{{.Names}}: {{.Status}}' | sort", show=False)
print(out6)
print(f"\n  URL publique: http://167.114.155.166")
print(f"  API publique: http://167.114.155.166:8010/health")
print(f"\n  NEXT: DNS tkverse.ca → 167.114.155.166 (Caddy prendra le relais)")

ssh.close()
