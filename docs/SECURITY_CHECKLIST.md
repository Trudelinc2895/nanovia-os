# ✅ CHECKLIST SÉCURITÉ PRÉ-PROD — KT Ecosystem
> Obligatoire avant tout déploiement en production. Zéro exception.
> Version: 2.0 | Maintenu par: Kevin Trudel | Scope: Tous projets

---

## 🔑 SECTION 1 — SECRETS & CREDENTIALS
- [ ] **S1** `.env` n'est PAS commité (vérifié via `git log --all -- .env`)
- [ ] **S2** `.gitignore` contient `.env`, `*.key`, `*.pem`, `secrets/`
- [ ] **S3** Tous les secrets sont des valeurs aléatoires fortes (min 32 chars)
- [ ] **S4** `SECRET_KEY` et `REFRESH_SECRET_KEY` sont différents et ≥ 256 bits
- [ ] **S5** Clés Stripe de production valides (pas de clés de test)
- [ ] **S6** Tokens/clés API rotatés dans les 30 derniers jours
- [ ] **S7** Aucun secret dans les logs, variables d'env publiques, ou commentaires
- [ ] **S8** TruffleHog scan passé sans résultat vérifié: `trufflehog git file://. --only-verified`

## 🐳 SECTION 2 — DOCKER & CONTAINERS
- [ ] **D1** Aucun container avec `privileged: true`
- [ ] **D2** Aucun port interne exposé sur `0.0.0.0` (utiliser `expose` seulement)
- [ ] **D3** Caddy est le seul service avec `ports: 80:80, 443:443`
- [ ] **D4** Images Docker avec tag précis (pas `latest` en prod)
- [ ] **D5** `restart: unless-stopped` sur tous les containers critiques
- [ ] **D6** Trivy scan passé: `trivy fs . --severity CRITICAL,HIGH --exit-code 1`
- [ ] **D7** `docker socket` non monté dans les containers applicatifs
- [ ] **D8** `POSTGRES_PASSWORD` défini et fort (≥ 24 chars aléatoires)

## 🌐 SECTION 3 — RÉSEAU & ACCÈS
- [ ] **N1** UFW actif: `ufw status` → only 22/80/443 open
- [ ] **N2** `PasswordAuthentication no` dans `/etc/ssh/sshd_config`
- [ ] **N3** fail2ban actif sur SSH: `fail2ban-client status sshd`
- [ ] **N4** nftables masqué: `systemctl is-enabled nftables` → masked
- [ ] **N5** Port 25 (SMTP) bloqué si pas de serveur mail
- [ ] **N6** Pas de règle UFW `allow from any` sans justification
- [ ] **N7** Root login SSH désactivé (ou key-only): `PermitRootLogin prohibit-password`

## 🔐 SECTION 4 — API & APPLICATION
- [ ] **A1** Tous les endpoints sensibles protégés par JWT (`Depends(get_current_user)`)
- [ ] **A2** Rate limiting activé sur `/auth/login` et `/auth/register`
- [ ] **A3** CORS configuré avec liste blanche stricte (pas `origins=["*"]`)
- [ ] **A4** Validation Pydantic sur tous les inputs (pas de `Any` non justifié)
- [ ] **A5** Passwords hashés avec Argon2id (jamais MD5/SHA1/bcrypt seul)
- [ ] **A6** JWT expire dans ≤ 30min (access token)
- [ ] **A7** Webhook Stripe vérifié avec `STRIPE_WEBHOOK_SECRET`
- [ ] **A8** Headers sécurité Caddy actifs: HSTS, CSP, X-Frame-Options

## 🗄️ SECTION 5 — BASE DE DONNÉES
- [ ] **B1** PostgreSQL non exposé publiquement (port 5432 interne uniquement)
- [ ] **B2** User DB avec permissions minimales (pas superuser pour l'app)
- [ ] **B3** Connexion via SSL/TLS si base distante
- [ ] **B4** Backup chiffré configuré et testé: `bash backup.sh test`
- [ ] **B5** Migrations testées sur copie de prod avant deploy

## 📊 SECTION 6 — MONITORING & ALERTES
- [ ] **M1** Prometheus + Grafana opérationnels
- [ ] **M2** Alertes Telegram configurées (CPU, RAM, Disk, API down)
- [ ] **M3** `/health` endpoint répond `{"status":"ok"}`
- [ ] **M4** CrowdSec ou fail2ban actif
- [ ] **M5** Logs centralisés et rotatifs (`logrotate`)

## 🔄 SECTION 7 — CI/CD & GITHUB
- [ ] **C1** Branch protection activée sur `main` (require PR + review)
- [ ] **C2** GitHub Actions security workflow passe sans erreur critique
- [ ] **C3** Secrets GitHub Actions dans `Settings > Secrets` (pas en dur)
- [ ] **C4** Dependabot activé pour alertes CVE
- [ ] **C5** CodeQL activé sur le repo

## 🏗️ SECTION 8 — INFRASTRUCTURE
- [ ] **I1** `nanovia-stack.service` autostart activé: `systemctl is-enabled nanovia-stack`
- [ ] **I2** `unattended-upgrades` actif pour patches automatiques
- [ ] **I3** Disque < 80% plein: `df -h /`
- [ ] **I4** Backup clé SSH stockée hors VPS (local + gestionnaire de mots de passe)
- [ ] **I5** OVH Manager: snapshots ou backups VPS activés

## �� RÉSUMÉ AVANT DEPLOY
```bash
# Commandes de vérification rapide (copier-coller sur VPS)
ssh root@167.114.155.166 "
  echo '=== UFW ===' && ufw status | grep -E 'Status|22|80|443'
  echo '=== SSH ===' && grep PasswordAuth /etc/ssh/sshd_config
  echo '=== Containers ===' && docker ps --format '{{.Names}} {{.Status}}'
  echo '=== Disk ===' && df -h / | tail -1
  echo '=== Health ===' && curl -s localhost:80/health
"
```

---
*Checklist générée le 2026-03-28 — Mise à jour requise à chaque nouvelle surface d'attaque*

