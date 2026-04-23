"""
Switch Caddy from HTTP-only to HTTPS after DNS propagation.

Required environment variables:
  VPS_HOST
  DEPLOY_PATH

Optional:
  VPS_USER=root
  VPS_KEY_PATH=~/.ssh/id_rsa
  APP_DOMAIN=nanovia.ca
  PUBLIC_IP=...
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

import paramiko

KEY = os.getenv("VPS_KEY_PATH", str(Path.home() / ".ssh" / "id_rsa"))
VPS = os.getenv("VPS_HOST", "")
VPS_USER = os.getenv("VPS_USER", "root")
DOMAIN = os.getenv("APP_DOMAIN", "nanovia.ca")
EXPECTED_IP = os.getenv("PUBLIC_IP", "")
DEPLOY_PATH = os.getenv("DEPLOY_PATH", "")
REPO_ROOT = Path(__file__).resolve().parents[1]


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 30) -> str:
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out or err


def main() -> int:
    if not VPS or not DEPLOY_PATH:
        raise SystemExit("Set VPS_HOST and DEPLOY_PATH before running switch_to_https.py")

    print("[1] Checking DNS...")
    response = urllib.request.urlopen(
        f"https://dns.google/resolve?name={DOMAIN}&type=A",
        timeout=5,
    )
    payload = json.loads(response.read())
    answers = [a["data"] for a in (payload.get("Answer") or []) if a["type"] == 1]

    if not answers:
        print(f"❌ {DOMAIN} still not resolving. Run setup_ovh_dns.py first, then wait ~5 min.")
        return 1

    if EXPECTED_IP and EXPECTED_IP not in answers:
        print(f"⚠️  {DOMAIN} resolves to {answers} — expected {EXPECTED_IP}")
        print("   Proceeding anyway...")
    else:
        print(f"✅ {DOMAIN} → {answers[0]}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS, username=VPS_USER, key_filename=KEY, timeout=15)

    print("[2] Replacing Caddyfile on VPS with HTTPS version...")
    with (REPO_ROOT / "infra" / "docker" / "Caddyfile.https").open("rb") as handle:
        content = handle.read()
    b64 = base64.b64encode(content).decode()
    run(ssh, f"echo '{b64}' | base64 -d > {DEPLOY_PATH}/infra/docker/Caddyfile")
    run(ssh, f"cp {DEPLOY_PATH}/infra/docker/Caddyfile {DEPLOY_PATH}/infra/docker/Caddyfile.bak")

    print("[3] Restarting Caddy with HTTPS config...")
    print(f"   {run(ssh, 'docker restart infra-caddy-1 2>&1')}")
    time.sleep(6)

    print("[4] Caddy TLS logs...")
    logs = run(ssh, "docker logs infra-caddy-1 --tail 8 2>&1")
    print(logs)

    if "error" in logs.lower() and "nxdomain" in logs.lower():
        print("\n⚠️  DNS still not propagated to Let's Encrypt. Wait 5 more min and retry.")
    elif "certificate" in logs.lower() or "tls" in logs.lower():
        print("\n✅ TLS cert acquisition in progress!")
    else:
        print("\n✅ Caddy restarted with HTTPS config.")

    print("\n[5] Testing HTTPS...")
    for target in [DOMAIN, f"api.{DOMAIN}"]:
        try:
            code = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"https://{target}", "--max-time", "5"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
            print(f"   https://{target} → HTTP {code}")
        except Exception:
            print(f"   https://{target} → timeout")

    ssh.close()
    print("\n=== HTTPS switch complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
