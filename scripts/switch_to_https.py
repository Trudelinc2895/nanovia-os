"""
Switch Caddy from HTTP-only to HTTPS (run after DNS propagates)
Usage: python scripts/switch_to_https.py
"""
import paramiko, shutil, os

KEY = r"C:\Users\Alienware\.ssh\id_rsa"
VPS = "167.114.155.166"

def run(ssh, cmd, timeout=30):
    _, o, e = ssh.exec_command(cmd, timeout=timeout)
    out = o.read().decode().strip()
    err = e.read().decode().strip()
    return out or err

print("[1] Checking DNS...")
import urllib.request, json
r = json.loads(urllib.request.urlopen(
    "https://dns.google/resolve?name=tkverse.ca&type=A", timeout=5
).read())
answers = [a["data"] for a in (r.get("Answer") or []) if a["type"] == 1]

if not answers:
    print("❌ tkverse.ca still not resolving. Run setup_ovh_dns.py first, then wait ~5 min.")
    exit(1)

if "167.114.155.166" not in answers:
    print(f"⚠️  tkverse.ca resolves to {answers} — expected 167.114.155.166")
    print("   Proceeding anyway...")
else:
    print(f"✅ tkverse.ca → {answers[0]}")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(VPS, username="root", key_filename=KEY, timeout=15)

print("[2] Replacing Caddyfile on VPS with HTTPS version...")
with open(r"C:\Users\Alienware\kt-monetization-os\infra\docker\Caddyfile.https", "rb") as f:
    content = f.read()

import base64
b64 = base64.b64encode(content).decode()
run(ssh, f"echo '{b64}' | base64 -d > /opt/kt-monetization-os/infra/docker/Caddyfile")
run(ssh, "cp /opt/kt-monetization-os/infra/docker/Caddyfile /opt/kt-monetization-os/infra/docker/Caddyfile.bak")

# Update docker-compose ports (remove 8020/9091 fallback ports)
print("[3] Restarting Caddy with HTTPS config...")
result = run(ssh, "docker restart infra-caddy-1 2>&1")
print(f"   {result}")

import time; time.sleep(6)

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
import subprocess
for domain in ["tkverse.ca", "api.tkverse.ca"]:
    try:
        code = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             f"https://{domain}", "--max-time", "5"],
            capture_output=True, text=True, timeout=10
        ).stdout
        print(f"   https://{domain} → HTTP {code}")
    except:
        print(f"   https://{domain} → timeout")

ssh.close()
print("\n=== HTTPS switch complete ===")
