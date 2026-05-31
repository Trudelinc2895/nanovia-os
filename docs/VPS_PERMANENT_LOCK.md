# VPS Permanent Lock

Nanovia now ships a final lockdown script for the production VPS:

`infra/scripts/lock-vps-forever.sh`

What it enforces:

1. deploy-only SSH access
2. root SSH disabled
3. password auth disabled
4. UFW default deny with SSH/80/443 allow rules
5. optional SSH source restriction with `--admin-ip`
6. fail2ban enabled for SSH
7. unattended security upgrades enabled
8. `.env` file ownership and `600` permissions
9. sysctl network hardening

Recommended execution order:

1. `fresh-install.sh`
2. `setup-deploy-user.sh`
3. verify deploy SSH key in a second session
4. `lock-vps-forever.sh`
5. `audit-vps-lockdown.sh`

Example:

```bash
sudo bash infra/scripts/lock-vps-forever.sh \
  --deploy-user deploy \
  --app-dir /opt/nanovia-os \
  --admin-ip YOUR_IP/32 \
  --public-key "ssh-ed25519 AAAA... nanovia-deploy"

sudo bash infra/scripts/audit-vps-lockdown.sh
```
