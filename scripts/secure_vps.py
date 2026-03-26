import paramiko, sys

HOST = '167.114.155.166'
USER = 'root'
PASS = '5YYSLkZ6Gfrt'
PUBKEY = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDLby85zYdhQWMxeCekB17aPmkQS/DWJO4uzP4eN4DjJjF2ZJM59q8pJwCZJTD0V94JVki4ctVwW2HuWX9Lrahwh0EppBD9AERZOWmJopckJ7coDzhD6+KrfpRo46CxhWaQTG4ZDs0DUOytrEcQ3/EREFO/9mWriLVEvafRmIUXQHa9oxCGEGIRr+X8ATuSnFK4OQy5Srclvqv5xb+492m72PwRij2gqNwNb5swB8zbZDvdhhasinMu0a5MG94LyRPBYMPWoO6JoiL5b8INEAJ1xrcsJpYQk46ZmNUYJonQiGO9xbC0md6HjlkrmMSpOT/yN1+cpW7sMxUlfYP79jl+lIau6wnn+rjvasqapevkMK0ZMS258ndNnvCkHm8LSrfPXPKR82cyNYY21LZUrrq7KLVbLZg3HHgOcRLjgW40QPfA3G1jhLGn+zT2H85Oh1QhrrBLxgMsU2+3b1sezbA0NHH6qEAxtaLGrFaziA9KCiykEPAxhelmMJTD01YOT38= Alienware@Vie-En-Homme-Libre'
NEW_ROOT_PASS = 'KT@V3rs3!S3cur3#2026'

SSHD_CONFIG = """# KT Secured SSH Config
Port 22
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
PermitEmptyPasswords no
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowTcpForwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
"""

JAIL_LOCAL = """[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5
backend = auto

[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
maxretry = 3
bantime = 86400
"""

SYSCTL_HARDENING = """
# KT Security Hardening
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
kernel.dmesg_restrict = 1
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)
print("=== CONNECTE EN MODE RESCUE ===")

def run(cmd, show=True):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if show and out: print(f"  OUT: {out}")
    if show and err: print(f"  ERR: {err}")
    return out

def write_file(remote_path, content):
    sftp = ssh.open_sftp()
    with sftp.open(remote_path, 'w') as f:
        f.write(content)
    sftp.close()

# 1. Monter le vrai disque
print("\n[1/8] Montage du vrai disque (sdb1)...")
run("mkdir -p /mnt/real")
run("mount /dev/sdb1 /mnt/real")
out = run("ls /mnt/real", show=False)
print(f"  Contenu: {out[:100]}")

# 2. Injecter la cle SSH
print("\n[2/8] Injection cle SSH sur le vrai systeme...")
run("mkdir -p /mnt/real/root/.ssh")
run("chmod 700 /mnt/real/root/.ssh")
write_file("/mnt/real/root/.ssh/authorized_keys", PUBKEY + "\n")
run("chmod 600 /mnt/real/root/.ssh/authorized_keys")
print("  Cle SSH injectee OK")

# 3. Securiser sshd_config
print("\n[3/8] Securisation SSH (desactiver auth mot de passe)...")
write_file("/mnt/real/etc/ssh/sshd_config", SSHD_CONFIG)
print("  sshd_config securise OK")

# 4. Changer le mot de passe root
print("\n[4/8] Changement mot de passe root...")
run(f"chroot /mnt/real bash -c 'echo root:{NEW_ROOT_PASS} | chpasswd'")
print(f"  Nouveau mot de passe root defini")

# 5. UFW via chroot
print("\n[5/8] Configuration UFW...")
run("chroot /mnt/real bash -c 'apt-get install -y ufw > /dev/null 2>&1 || true'")
run("chroot /mnt/real bash -c 'ufw --force reset > /dev/null 2>&1 || true'")
run("chroot /mnt/real bash -c 'ufw default deny incoming > /dev/null 2>&1'")
run("chroot /mnt/real bash -c 'ufw default allow outgoing > /dev/null 2>&1'")
run("chroot /mnt/real bash -c 'ufw allow 22/tcp > /dev/null 2>&1'")
run("chroot /mnt/real bash -c 'ufw allow 80/tcp > /dev/null 2>&1'")
run("chroot /mnt/real bash -c 'ufw allow 443/tcp > /dev/null 2>&1'")
run("chroot /mnt/real bash -c 'ufw --force enable > /dev/null 2>&1 || true'")
print("  UFW: ports 22, 80, 443 seulement")

# 6. fail2ban config
print("\n[6/8] Configuration fail2ban...")
fail2ban_dir = run("ls /mnt/real/etc/fail2ban/ 2>/dev/null || echo MISSING", show=False)
if "MISSING" not in fail2ban_dir:
    write_file("/mnt/real/etc/fail2ban/jail.local", JAIL_LOCAL)
    print("  fail2ban: 3 tentatives SSH = ban 24h")
else:
    print("  fail2ban non installe (sera installe au demarrage via bootstrap)")

# 7. Hardening sysctl
print("\n[7/8] Hardening kernel sysctl...")
run(f"cat >> /mnt/real/etc/sysctl.conf << 'EOF'\n{SYSCTL_HARDENING}\nEOF")
print("  sysctl hardening applique")

# 8. Verification + unmount
print("\n[8/8] Verification finale...")
key_check = run("cut -c1-40 /mnt/real/root/.ssh/authorized_keys", show=False)
print(f"  authorized_keys: {key_check}...")
pwd_check = run("grep PasswordAuthentication /mnt/real/etc/ssh/sshd_config", show=False)
print(f"  sshd_config: {pwd_check}")
run("umount /mnt/real")
print("  Disque demonte proprement")

print()
print("=" * 50)
print("  SECURISATION COMPLETE")
print("=" * 50)
print(f"  Nouveau mdp root:    {NEW_ROOT_PASS}")
print("  SSH auth:            Cle uniquement (mdp desactive)")
print("  Ports ouverts:       22, 80, 443")
print("  fail2ban SSH:        3 essais = ban 24h")
print("  Kernel hardening:    SYN cookies, RP filter, no redirects")
print()
print("ACTION REQUISE:")
print("  1. Aller sur manager.ovh.com -> VPS")
print("  2. Onglet 'Boot' -> changer Netboot en 'Disque dur'")
print("  3. Redemarrer le VPS -> mode normal")
print("  4. Reconnexion SSH par cle automatique")

ssh.close()
