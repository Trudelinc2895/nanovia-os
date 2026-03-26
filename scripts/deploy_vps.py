#!/usr/bin/env python3
"""Déploiement final: git pull + docker compose avec --env-file correct."""
import paramiko, time, re

HOST = '167.114.155.166'
USER = 'root'
KEY_PATH = r'C:\Users\Alienware\.ssh\id_rsa'

def run(ssh, cmd, timeout=600, show=True):
    chan = ssh.get_transport().open_session()
    chan.set_combine_stderr(True)
    chan.exec_command(cmd)
    out = b''
    while True:
        if chan.recv_ready():
            chunk = chan.recv(8192)
            out += chunk
            if show:
                text = re.sub(r'\x1b\[[0-9;]*[mGKHF]|\r', '', chunk.decode('utf-8', 'replace'))
                print(text.encode("utf-8","replace").decode("utf-8"), end='', flush=True)
        elif chan.exit_status_ready():
            while chan.recv_ready():
                out += chan.recv(8192)
            break
        else:
            time.sleep(0.3)
    return chan.recv_exit_status(), re.sub(r'\x1b\[[0-9;]*[mGKHF]|\r', '', out.decode('utf-8', 'replace'))

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
print(f"=== DEPLOY: {HOST} ===\n")

print("[1/4] git pull origin main...")
rc, out = run(ssh, "cd /opt/kt-monetization-os && git pull origin main 2>&1", show=False)
print(f"  {out.strip()[-200:]}")

print("\n[2/4] Vérification .env...")
rc, out = run(ssh, "grep -E '^DOMAIN=|^POSTGRES_PASSWORD=|^POSTGRES_DB=' /opt/kt-monetization-os/.env", show=False)
print(f"  {out.strip()}")

print("\n[3/4] Docker Compose up (--env-file explicite)...")
print("  Build en cours — Next.js peut prendre 2-3 min...\n")
COMPOSE_CMD = (
    "cd /opt/kt-monetization-os && "
    "docker compose -f infra/docker-compose.prod.yml "
    "--env-file /opt/kt-monetization-os/.env "
    "up -d --build 2>&1"
)
rc, out = run(ssh, COMPOSE_CMD, timeout=600)

print("\n\n[4/4] Status final...")
rc2, out2 = run(ssh, "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", show=False)
print(out2)

time.sleep(8)
print("\n=== TESTS SANTÉ ===")
for path, port in [("/health", 8010), ("/", 3000), ("/health", 3020), ("/health", 8020)]:
    rc3, out3 = run(ssh, f"curl -s --max-time 5 http://localhost:{port}{path} 2>/dev/null || echo 'TIMEOUT'", show=False)
    status = "✅" if "ok" in out3 or "html" in out3.lower() or "KT" in out3 else "⏳"
    print(f"  {status} :{port}{path} → {out3.strip()[:80]}")

print("\n=== RÉSUMÉ ===")
print("  http://167.114.155.166      → Web (port 80 via Caddy si DNS ok)")
print("  http://167.114.155.166:8010 → API FastAPI directe")
print("  http://167.114.155.166:3000 → Next.js direct")
print("\n  NEXT: Configurer DNS tkverse.ca → 167.114.155.166")

ssh.close()

