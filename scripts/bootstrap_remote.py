"""
Bootstrap VPS via Paramiko SSH.

Required environment variables:
  VPS_HOST
  DEPLOY_PATH
  APP_REPO_URL

Optional:
  VPS_USER=root
  VPS_KEY_PATH=~/.ssh/id_rsa
  APP_ENV_FILE=./.env
  APP_DOMAIN=...
  PUBLIC_IP=...
"""

from __future__ import annotations

import os
from pathlib import Path
import time

import paramiko

HOST = os.getenv("VPS_HOST", "")
USER = os.getenv("VPS_USER", "root")
KEY_PATH = os.getenv("VPS_KEY_PATH", str(Path.home() / ".ssh" / "id_rsa"))
DEPLOY_PATH = os.getenv("DEPLOY_PATH", "")
REPO_URL = os.getenv("APP_REPO_URL", "")
PUBLIC_DOMAIN = os.getenv("APP_DOMAIN", "")
PUBLIC_IP = os.getenv("PUBLIC_IP", "")
ENV_PATH = os.getenv("APP_ENV_FILE", str(Path(__file__).resolve().parents[1] / ".env"))

if not HOST or not DEPLOY_PATH or not REPO_URL:
    raise SystemExit("Set VPS_HOST, DEPLOY_PATH and APP_REPO_URL before running bootstrap_remote.py")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
print("=== VPS CONNECTE PAR CLE SSH ===")
print(f"Host: {HOST}")


def run(cmd: str, timeout: int = 120, show: bool = True):
    print(f"\n$ {cmd[:80]}...")
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.set_combine_stderr(False)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    rc = stdout.channel.recv_exit_status()
    if show and out:
        print(out[-2000:])
    if err and "WARNING" not in err and rc != 0:
        print(f"  STDERR: {err[-500:]}")
    return rc, out, err


def step(msg: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {msg}")
    print("=" * 50)


step("1/8 — INFO SYSTÈME")
run("lsb_release -d && uname -r && df -h / && free -h")

step("2/8 — APT UPDATE + DÉPENDANCES")
run("apt-get update -qq", timeout=120)
run("apt-get install -y -qq curl wget git unzip ufw fail2ban htop", timeout=180)
print("  Paquets de base installés ✅")

step("3/8 — DOCKER ENGINE")
rc, out, _ = run("docker --version 2>/dev/null", show=False)
if rc == 0:
    print(f"  Docker déjà installé: {out} ✅")
else:
    print("  Installation Docker...")
    run("curl -fsSL https://get.docker.com | sh", timeout=300)
    run("systemctl enable docker && systemctl start docker")
    _, out2, _ = run("docker --version", show=False)
    print(f"  Docker installé: {out2} ✅")

rc, _, _ = run("docker compose version 2>/dev/null", show=False)
if rc != 0:
    run("apt-get install -y docker-compose-plugin", timeout=120)
_, out4, _ = run("docker compose version", show=False)
print(f"  {out4} ✅")

step("4/8 — UFW FIREWALL")
run("ufw --force reset")
run("ufw default deny incoming")
run("ufw default allow outgoing")
run("ufw allow 22/tcp comment 'SSH'")
run("ufw allow 80/tcp comment 'HTTP'")
run("ufw allow 443/tcp comment 'HTTPS'")
run("ufw --force enable")
_, out5, _ = run("ufw status", show=False)
print(out5)
print("  UFW actif: 22/80/443 ✅")

step("5/8 — FAIL2BAN")
run("systemctl enable fail2ban && systemctl start fail2ban 2>/dev/null || true")
_, out6, _ = run("fail2ban-client status 2>/dev/null || echo 'starting'", show=False)
print(f"  fail2ban: {out6[:80]} ✅")

step("6/8 — CLONE REPO")
run(f"mkdir -p {DEPLOY_PATH}")
_, out7, _ = run(f"ls {DEPLOY_PATH}/backend 2>/dev/null && echo EXISTS || echo EMPTY", show=False)
if "EXISTS" in out7:
    print("  Repo déjà présent — git pull...")
    run(f"cd {DEPLOY_PATH} && git pull origin main 2>&1")
else:
    print("  Clonage du repo...")
    run(f"git clone {REPO_URL} {DEPLOY_PATH}", timeout=120)
_, out8, _ = run(f"ls {DEPLOY_PATH}/", show=False)
print(f"  Contenu: {out8[:150]} ✅")

step("7/8 — COPIE .env")
if os.path.exists(ENV_PATH):
    sftp = ssh.open_sftp()
    sftp.put(ENV_PATH, f"{DEPLOY_PATH}/.env")
    sftp.close()
    print("  .env copié via SFTP ✅")
else:
    print("  ATTENTION: .env introuvable localement!")

step("8/8 — DOCKER COMPOSE PROD")
run(f"cd {DEPLOY_PATH} && docker compose -f infra/docker-compose.prod.yml pull 2>&1 || true", timeout=300)
run(f"cd {DEPLOY_PATH} && docker compose -f infra/docker-compose.prod.yml up -d --build 2>&1", timeout=600)
time.sleep(5)
_, out9, _ = run(f"docker compose -f {DEPLOY_PATH}/infra/docker-compose.prod.yml ps", show=False)
print(out9)

print("\n" + "=" * 50)
print("  BOOTSTRAP COMPLET")
print("=" * 50)
_, out10, _ = run("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", show=False)
print(out10)
print()
print("  Accès:")
print(f"  http://{HOST}        → Landing page")
print(f"  http://{HOST}/api/health → API health")
if PUBLIC_DOMAIN and PUBLIC_IP:
    print()
    print(f"  NEXT: Configurer DNS {PUBLIC_DOMAIN} → {PUBLIC_IP}")

ssh.close()
