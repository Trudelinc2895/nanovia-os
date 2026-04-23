"""Compatibility bootstrap helper for Nanovia VPS provisioning."""

from __future__ import annotations

import base64
import os
import re
import time
from pathlib import Path

import paramiko

HOST = os.getenv("VPS_HOST", "")
USER = os.getenv("VPS_USER", "root")
KEY_PATH = os.getenv("VPS_KEY_PATH", str(Path.home() / ".ssh" / "id_rsa"))
ENV_PATH = os.getenv("APP_ENV_FILE", str(Path(__file__).resolve().parents[1] / ".env"))
DEPLOY_PATH = os.getenv("DEPLOY_PATH", "")
REPO_URL = os.getenv("APP_REPO_URL", "")
PUBLIC_DOMAIN = os.getenv("APP_DOMAIN", "")
PUBLIC_IP = os.getenv("PUBLIC_IP", "")

if not HOST or not DEPLOY_PATH or not REPO_URL:
    raise SystemExit("Set VPS_HOST, DEPLOY_PATH and APP_REPO_URL before running bootstrap_v4.py")


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 600, show: bool = True):
    chan = ssh.get_transport().open_session()
    chan.set_combine_stderr(True)
    chan.exec_command(cmd)
    out = b""
    while True:
        if chan.recv_ready():
            chunk = chan.recv(8192)
            out += chunk
            if show:
                text = re.sub(r"\x1b\[[0-9;]*[mGKHF]|\r", "", chunk.decode("utf-8", "replace"))
                print(text.encode("utf-8", "replace").decode("utf-8"), end="", flush=True)
        elif chan.exit_status_ready():
            while chan.recv_ready():
                out += chan.recv(8192)
            break
        else:
            time.sleep(0.3)
    return chan.recv_exit_status(), re.sub(r"\x1b\[[0-9;]*[mGKHF]|\r", "", out.decode("utf-8", "replace"))


ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
print(f"=== CONNECTE: {HOST} ===\n")

print("[0] Fix sshd_config + reload SSH...")
sshd_config = """Port 22
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
encoded = base64.b64encode(sshd_config.encode()).decode()
run(ssh, f"echo '{encoded}' | base64 -d > /etc/ssh/sshd_config", show=False)
_, out = run(ssh, "sshd -t && systemctl reload ssh && echo SSH_RELOADED || echo SSH_RELOAD_FAILED", show=False)
print(f"  {out.strip()}")

print("\n[1] Git clone (dossier existant — git init + pull)...")
cmds = [
    f"cp {DEPLOY_PATH}/.env /tmp/.env.backup 2>/dev/null || true",
    f"cd {DEPLOY_PATH} && git init",
    f"cd {DEPLOY_PATH} && git remote add origin {REPO_URL} 2>/dev/null || git remote set-url origin {REPO_URL}",
    f"cd {DEPLOY_PATH} && git fetch origin main",
    f"cd {DEPLOY_PATH} && git reset --hard origin/main",
    f"cp /tmp/.env.backup {DEPLOY_PATH}/.env 2>/dev/null || true",
]
for cmd in cmds:
    rc, _ = run(ssh, cmd, show=False)
    label = cmd.split("&&")[-1].strip()[:60]
    print(f"  {'✅' if rc == 0 else '⚠️'} {label}")

_, out = run(ssh, f"ls {DEPLOY_PATH}/", show=False)
print(f"  Contenu: {out.strip()[:120]}")

print("\n[2] Vérification .env...")
_, out = run(ssh, f"wc -l {DEPLOY_PATH}/.env && head -3 {DEPLOY_PATH}/.env", show=False)
print(f"  {out.strip()}")

print("\n[3] Fix SSH service (Ubuntu 24 = 'ssh' pas 'sshd')...")
_, out = run(ssh, "systemctl status ssh --no-pager -l | head -5", show=False)
print(f"  {out.strip()[:200]}")

print("\n[4] Docker Compose up (peut prendre 3-5 min)...")
print("  Pull images...\n")
run(ssh, f"cd {DEPLOY_PATH} && docker compose -f infra/docker-compose.prod.yml pull 2>&1", timeout=600)
print("\n  Build + up...\n")
run(ssh, f"cd {DEPLOY_PATH} && docker compose -f infra/docker-compose.prod.yml up -d --build 2>&1", timeout=600)

print("\n\n=== DOCKER STATUS ===")
_, out = run(ssh, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", show=False)
print(out)

print("\n[5] Test API health...")
time.sleep(8)
_, out = run(ssh, "curl -s http://localhost:8010/health 2>/dev/null || echo 'API pas encore prête'", show=False)
print(f"  GET /health → {out.strip()}")
_, out = run(ssh, "curl -s http://localhost:8010/ 2>/dev/null || echo 'Root pas encore prêt'", show=False)
print(f"  GET / → {out.strip()[:100]}")

print("\n=== RÉSUMÉ VPS ===")
_, out = run(ssh, "docker ps --format '{{.Names}}: {{.Status}}' | sort", show=False)
print(out)
print(f"\n  URL publique: http://{HOST}")
print(f"  API publique: http://{HOST}:8010/health")
if PUBLIC_DOMAIN and PUBLIC_IP:
    print(f"\n  NEXT: DNS {PUBLIC_DOMAIN} → {PUBLIC_IP} (Caddy prendra le relais)")

ssh.close()
