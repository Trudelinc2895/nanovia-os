#!/usr/bin/env python3
"""Déploiement final: git pull + docker compose avec --env-file correct."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import paramiko

HOST = os.getenv("VPS_HOST", "")
USER = os.getenv("VPS_USER", "root")
KEY_PATH = os.getenv("VPS_KEY_PATH", str(Path.home() / ".ssh" / "id_rsa"))
DEPLOY_PATH = os.getenv("DEPLOY_PATH", "")
PUBLIC_DOMAIN = os.getenv("APP_DOMAIN", "")
PUBLIC_IP = os.getenv("PUBLIC_IP", "")

if not HOST or not DEPLOY_PATH:
    raise SystemExit("Set VPS_HOST and DEPLOY_PATH before running deploy_vps.py")


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
print(f"=== DEPLOY: {HOST} ===\n")

print("[1/4] git pull origin main...")
_, out = run(ssh, f"cd {DEPLOY_PATH} && git pull origin main 2>&1", show=False)
print(f"  {out.strip()[-200:]}")

print("\n[2/4] Vérification .env...")
_, out = run(ssh, f"grep -E '^DOMAIN=|^POSTGRES_PASSWORD=|^POSTGRES_DB=' {DEPLOY_PATH}/.env", show=False)
print(f"  {out.strip()}")

print("\n[3/4] Docker Compose up (--env-file explicite)...")
print("  Build en cours — Next.js peut prendre 2-3 min...\n")
compose_cmd = (
    f"cd {DEPLOY_PATH} && "
    "docker compose -f infra/docker-compose.prod.yml "
    f"--env-file {DEPLOY_PATH}/.env "
    "up -d --build 2>&1"
)
run(ssh, compose_cmd, timeout=600)

print("\n\n[4/4] Status final...")
_, out2 = run(ssh, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", show=False)
print(out2)

time.sleep(8)
print("\n=== TESTS SANTÉ ===")
for path, port in [("/health", 8010), ("/", 3000), ("/health", 3020), ("/health", 8020)]:
    _, out3 = run(ssh, f"curl -s --max-time 5 http://localhost:{port}{path} 2>/dev/null || echo 'TIMEOUT'", show=False)
    status = "✅" if "ok" in out3 or "html" in out3.lower() or "Nanovia" in out3 else "⏳"
    print(f"  {status} :{port}{path} → {out3.strip()[:80]}")

print("\n=== RÉSUMÉ ===")
print(f"  http://{HOST}      → Web (port 80 via Caddy si DNS ok)")
print(f"  http://{HOST}:8010 → API FastAPI directe")
print(f"  http://{HOST}:3000 → Next.js direct")
if PUBLIC_DOMAIN and PUBLIC_IP:
    print(f"\n  NEXT: Configurer DNS {PUBLIC_DOMAIN} → {PUBLIC_IP}")

ssh.close()
