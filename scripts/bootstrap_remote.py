"""
Bootstrap VPS complet via Paramiko SSH.
Installe Docker, clone le repo, copie .env, lance docker compose.
"""
import paramiko, time, sys, os

HOST = '167.114.155.166'
USER = 'root'
KEY_PATH = r'C:\Users\Alienware\.ssh\id_rsa'

# Charger le .env local pour le copier sur le VPS
ENV_PATH = r'C:\Users\Alienware\kt-monetization-os\.env'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
print("=== VPS CONNECTE PAR CLE SSH ===")
print(f"Host: {HOST}")

def run(cmd, timeout=120, show=True):
    print(f"\n$ {cmd[:80]}...")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    stdout.channel.set_combine_stderr(False)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    rc = stdout.channel.recv_exit_status()
    if show and out: print(out[-2000:])  # dernières 2000 chars
    if err and 'WARNING' not in err and rc != 0:
        print(f"  STDERR: {err[-500:]}")
    return rc, out, err

def step(msg):
    print(f"\n{'='*50}")
    print(f"  {msg}")
    print('='*50)

# ── STEP 1: Info système ────────────────────────────
step("1/8 — INFO SYSTÈME")
run("lsb_release -d && uname -r && df -h / && free -h")

# ── STEP 2: Update & dépendances de base ───────────
step("2/8 — APT UPDATE + DÉPENDANCES")
run("apt-get update -qq", timeout=120)
run("apt-get install -y -qq curl wget git unzip ufw fail2ban htop", timeout=180)
print("  Paquets de base installés ✅")

# ── STEP 3: Docker Engine ──────────────────────────
step("3/8 — DOCKER ENGINE")
rc, out, _ = run("docker --version 2>/dev/null", show=False)
if rc == 0:
    print(f"  Docker déjà installé: {out} ✅")
else:
    print("  Installation Docker...")
    run("curl -fsSL https://get.docker.com | sh", timeout=300)
    run("systemctl enable docker && systemctl start docker")
    rc2, out2, _ = run("docker --version", show=False)
    print(f"  Docker installé: {out2} ✅")

# Docker Compose v2
rc3, out3, _ = run("docker compose version 2>/dev/null", show=False)
if rc3 != 0:
    run("apt-get install -y docker-compose-plugin", timeout=120)
rc4, out4, _ = run("docker compose version", show=False)
print(f"  {out4} ✅")

# ── STEP 4: UFW Firewall ───────────────────────────
step("4/8 — UFW FIREWALL")
run("ufw --force reset")
run("ufw default deny incoming")
run("ufw default allow outgoing")
run("ufw allow 22/tcp comment 'SSH'")
run("ufw allow 80/tcp comment 'HTTP'")
run("ufw allow 443/tcp comment 'HTTPS'")
run("ufw --force enable")
rc5, out5, _ = run("ufw status", show=False)
print(out5)
print("  UFW actif: 22/80/443 ✅")

# ── STEP 5: fail2ban ──────────────────────────────
step("5/8 — FAIL2BAN")
run("systemctl enable fail2ban && systemctl start fail2ban 2>/dev/null || true")
rc6, out6, _ = run("fail2ban-client status 2>/dev/null || echo 'starting'", show=False)
print(f"  fail2ban: {out6[:80]} ✅")

# ── STEP 6: Clone du repo ─────────────────────────
step("6/8 — CLONE REPO kt-monetization-os")
run("mkdir -p /opt/kt-monetization-os")
rc7, out7, _ = run("ls /opt/kt-monetization-os/backend 2>/dev/null && echo EXISTS || echo EMPTY", show=False)
if "EXISTS" in out7:
    print("  Repo déjà présent — git pull...")
    run("cd /opt/kt-monetization-os && git pull origin main 2>&1")
else:
    print("  Clonage du repo...")
    run("git clone https://github.com/Trudelinc2895/kt-monetization-os.git /opt/kt-monetization-os", timeout=120)
rc8, out8, _ = run("ls /opt/kt-monetization-os/", show=False)
print(f"  Contenu: {out8[:150]} ✅")

# ── STEP 7: Copier .env sur le VPS ────────────────
step("7/8 — COPIE .env")
if os.path.exists(ENV_PATH):
    sftp = ssh.open_sftp()
    sftp.put(ENV_PATH, '/opt/kt-monetization-os/.env')
    sftp.close()
    print("  .env copié via SFTP ✅")
else:
    print("  ATTENTION: .env introuvable localement!")

# ── STEP 8: Docker Compose up ─────────────────────
step("8/8 — DOCKER COMPOSE PROD")
run("cd /opt/kt-monetization-os && docker compose -f infra/docker-compose.prod.yml pull 2>&1 || true", timeout=300)
run("cd /opt/kt-monetization-os && docker compose -f infra/docker-compose.prod.yml up -d --build 2>&1", timeout=600)
time.sleep(5)
rc9, out9, _ = run("docker compose -f /opt/kt-monetization-os/infra/docker-compose.prod.yml ps", show=False)
print(out9)

# ── Résumé ─────────────────────────────────────────
print("\n" + "="*50)
print("  BOOTSTRAP COMPLET")
print("="*50)
rc10, out10, _ = run("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", show=False)
print(out10)
print()
print("  Accès:")
print(f"  http://{HOST}        → Landing page")
print(f"  http://{HOST}/api/health → API health")
print()
print("  NEXT: Configurer DNS tkverse.ca → 167.114.155.166")

ssh.close()
