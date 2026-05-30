# 🛡️ NANOVIA SECURITY MASTER — Audit & Plan de Sécurisation Complet
## Périmètre: Tous projets actuels et futurs | Niveau: MAXIMAL
## Dernière mise à jour: 2026-03-27

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 1. CARTOGRAPHIE DES RISQUES (Risk Map)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🔴 CRITIQUE (action immédiate)
| ID | Risque | Vecteur | Impact |
|---|---|---|---|
| R01 | Mot de passe root VPS exposé | SSH brute-force | Compromission totale serveur |
| R02 | Clés API dans .env non chiffré | Fuite repo / accès serveur | Frais illimités Stripe/OpenAI |
| R03 | DNS A records manquants | NXDOMAIN | Indisponibilité totale service |
| R04 | Containers Docker sans restart policy | Crash silencieux | Downtime non détecté |
| R05 | Pas de backup automatique PostgreSQL | Panne disque / erreur humaine | Perte données irréversible |

### 🟠 ÉLEVÉ (< 7 jours)
| ID | Risque | Vecteur | Impact |
|---|---|---|---|
| R06 | JWT secret_key faible ou par défaut | Brute-force token | Impersonation utilisateurs |
| R07 | PasswordAuthentication SSH activée | Brute-force SSH | Accès root non autorisé |
| R08 | Pas de rotation automatique des secrets | Secret exposé indéfiniment | Compromission silencieuse |
| R09 | Webhook Stripe sans validation IP source | Replay attack | Fraude abonnements |
| R10 | Grafana admin sans 2FA | Accès dashboard | Exposition métriques sensibles |

### 🟡 MOYEN (< 30 jours)
| ID | Risque | Vecteur | Impact |
|---|---|---|---|
| R11 | Pas de WAF applicatif (rate-limit global) | DDoS / flood API | Indisponibilité + coûts |
| R12 | Logs non centralisés | Incident non détecté | Réponse tardive |
| R13 | Pas de scan SAST automatique sur PR | Vulnérabilités en production | Exploitation code |
| R14 | CORS trop permissif en dev | Cross-origin attack | Fuite tokens |
| R15 | Pas de politique de mots de passe utilisateurs | Comptes faibles | Compromission masse |

### 🟢 FAIBLE (< 90 jours)
| ID | Risque | Vecteur | Impact |
|---|---|---|---|
| R16 | Pas de tests de pénétration | Vulnérabilités inconnues | Découverte par attaquant |
| R17 | Pas de politique de rétention des logs | Stockage illimité | Coûts + conformité |
| R18 | Dépendances NPM/pip non auditées régulièrement | Supply chain attack | Code malveillant |

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 2. ÉTAT ACTUEL — CE QUI EST DÉPLOYÉ
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### ✅ Sécurité déjà en place (Nanovia OS)
```
RÉSEAU
  ✅ UFW: 22/80/443 uniquement
  ✅ Docker: ports liés à 127.0.0.1 (pas 0.0.0.0)
  ✅ nftables: supprimé (conflit résolu définitivement)
  ✅ fail2ban: SSH + HTTP (MaxRetry=3, bantime=6h)
  ✅ crowdsec: IPS actif
  ✅ PSAD: détection port scan

APPLICATION
  ✅ Argon2id: hashing mots de passe (meilleur 2024)
  ✅ JWT HS256: access (30min) + refresh (7j) tokens
  ✅ Rate limiting Redis: auth 10/min, user 100/min, anon 30/min
  ✅ CORS: domaines spécifiques uniquement
  ✅ Webhook Stripe: signature HMAC vérifiée (raw body)
  ✅ Idempotency: webhook_events table (duplicates ignorés)

CADDY (reverse proxy)
  ✅ HTTPS automatique Let's Encrypt
  ✅ HSTS preload (max-age=31536000; includeSubDomains)
  ✅ CSP strict
  ✅ WAF rules: block scanners, SQLi, path traversal, bad methods
  ✅ Rate limit: 100 req/min par IP sur api.nanovia.ca
  ✅ Security headers: X-Frame DENY, X-Content-Type-Options, etc.

CI/CD SÉCURITÉ
  ✅ Bandit: SAST Python
  ✅ Safety: scan dépendances vulnérables
  ✅ Trivy: scan containers
  ✅ CodeQL: GitHub Actions
  ✅ Secrets scanning: GitHub native

MONITORING
  ✅ Prometheus: métriques temps réel
  ✅ Alertmanager: Telegram alerts
  ✅ 12 règles: CPU/RAM/Disk/API/DB/Security
  ✅ Grafana: dashboard KPI complet
  ✅ node-exporter + postgres-exporter + redis-exporter

HARDENING SYSTÈME
  ✅ sysctl kernel hardening
  ✅ AppArmor Docker profiles
  ✅ rkhunter + chkrootkit
  ✅ AIDE file integrity
  ✅ SSH: MaxAuthTries=2, PermitRootLogin prohibit-password
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 3. PLAN D'ACTION DÉTAILLÉ
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🔴 IMMÉDIAT (aujourd'hui)

| # | Action | Commande / Lieu |
|---|---|---|
| A01 | Désactiver SSH password auth après clé ajoutée | `sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config` |
| A02 | Ajouter DNS A records OVH | OVH Manager → Zone DNS → 6 enregistrements → 167.114.155.166 |
| A03 | Vérifier .env: secrets forts générés | `openssl rand -hex 32` pour SECRET_KEY |
| A04 | Activer backup PostgreSQL automatique | Script `backup-db.sh` (voir Section 5) |

### 🟠 SEMAINE 1 (< 7 jours)

| # | Action | Priorité |
|---|---|---|
| B01 | Activer GitHub 2FA obligatoire | Compte GitHub → Settings → 2FA |
| B02 | Activer OVH 2FA | OVH Manager → Mon compte → 2FA |
| B03 | Rotation secrets: générer nouveaux JWT keys en prod | Script `rotate-secrets.sh` |
| B04 | Configurer Stripe webhook IP whitelist | Stripe Dashboard → Webhooks → restrict to Stripe IPs |
| B05 | Setup Telegram bot pour alertes Prometheus | Variables TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID dans .env |

### 🟡 30 JOURS

| # | Action | Priorité |
|---|---|---|
| C01 | Sauvegardes automatiques DB vers stockage externe (S3/Backblaze) | `restic` ou `rclone` |
| C02 | Audit dépendances NPM/pip hebdomadaire | `npm audit` + `pip-audit` en CI |
| C03 | Politique mots de passe utilisateurs: min 12 chars, complexity | Backend validation |
| C04 | Logs centralisés: Loki + Grafana | Ajouter Loki au docker-compose |
| C05 | Test de restauration backup | Simuler perte DB → restaurer depuis backup |

### 🔵 90 JOURS

| # | Action | Priorité |
|---|---|---|
| D01 | Test de pénétration (pentest) | OWASP ZAP auto-scan ou service externe |
| D02 | Conformité RGPD: audit données personnelles | Politique rétention + droit à l'effacement |
| D03 | Disaster Recovery: documenter RTO=2h RPO=1h | Playbooks testés |
| D04 | Security scoring automatique par projet | Script d'audit dans CI/CD |
| D05 | Revue sécurité trimestrielle | Calendrier fixe |

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 4. POLITIQUE SÉCURITÉ UNIVERSELLE
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
### Obligatoire sur TOUS les projets (présents et futurs)

```
IDENTITÉ & ACCÈS
  □ MFA activé: GitHub, OVH, Stripe, tous comptes sensibles
  □ Principe moindre privilège: chaque service = son propre compte limité
  □ Pas de root en production sauf pour maintenance
  □ SSH: clés uniquement (no password), ed25519 préféré
  □ Secrets: jamais dans le code, toujours dans .env (gitignored)
  □ Rotation secrets: tous les 90 jours minimum

CODE & BUILD
  □ .gitignore: .env, *.key, *.pem, secrets/
  □ Pre-commit hooks: detect-secrets, bandit
  □ GitHub Actions: Bandit + Safety + Trivy sur chaque PR
  □ Branch protection: PR required, no direct push to main
  □ Dependabot: activé pour toutes les dépendances

INFRASTRUCTURE
  □ Firewall: UFW par défaut (deny all, allow 22/80/443)
  □ Docker: ports liés à 127.0.0.1, jamais 0.0.0.0
  □ fail2ban: actif dès la première installation
  □ HTTPS: obligatoire, HTTP redirige vers HTTPS
  □ Headers: HSTS, CSP, X-Frame, X-Content-Type
  □ Mises à jour: unattended-upgrades activé

APPLICATION
  □ Auth: JWT avec expiration courte (≤ 30min access)
  □ Passwords: Argon2id (jamais bcrypt, jamais MD5/SHA1)
  □ Rate limiting: par endpoint, par IP, par utilisateur
  □ CORS: whitelist explicite, jamais *
  □ Input validation: pydantic/zod strict, jamais eval()
  □ SQL: ORM uniquement, jamais de raw queries avec input utilisateur

DONNÉES
  □ Chiffrement au repos: PostgreSQL sur disque chiffré (OVH option)
  □ Chiffrement transit: TLS 1.3 minimum
  □ Backup: quotidien, testé mensuellement, stockage externe
  □ Logs: pas de données sensibles dans les logs (no passwords, no tokens)

MONITORING
  □ Alertes: CPU>85%, RAM>85%, disk>80%, service down
  □ Telegram bot configuré pour alertes critiques
  □ Uptime monitoring (UptimeRobot gratuit en backup)
  □ Revue logs hebdomadaire
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 5. SCRIPTS SÉCURITÉ CLÉS
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### backup-db.sh (à exécuter quotidiennement via cron)
```bash
#!/bin/bash
# Backup PostgreSQL → fichier chiffré local + upload externe optionnel
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backups/postgres"
mkdir -p $BACKUP_DIR
docker exec infra-postgres-1 pg_dump -U kt_user kt_monetization | \
  gzip | \
  openssl enc -aes-256-cbc -pbkdf2 -k "$BACKUP_ENCRYPTION_KEY" \
  > "$BACKUP_DIR/kt_db_$DATE.sql.gz.enc"
# Keep only last 7 days
find $BACKUP_DIR -name "*.enc" -mtime +7 -delete
echo "Backup: $BACKUP_DIR/kt_db_$DATE.sql.gz.enc"
```

### Cron (ajouter avec `crontab -e`):
```
0 2 * * * /opt/nanovia-os/infra/scripts/backup-db.sh >> /var/log/nanovia-backup.log 2>&1
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 6. CHECKLIST AVANT MISE EN PRODUCTION
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
### À valider pour CHAQUE nouveau projet / déploiement

```
SÉCURITÉ CODE
  □ Pas de secrets dans le code (scan secret = 0 résultat)
  □ .env dans .gitignore
  □ Bandit = 0 issues High/Critical
  □ Safety = 0 vulnérabilités critiques
  □ npm audit = 0 vulnérabilités High/Critical

INFRASTRUCTURE  
  □ UFW actif (ufw status = active)
  □ fail2ban actif (systemctl is-active fail2ban = active)
  □ HTTPS configuré (curl -I https://domain → 200)
  □ HTTP redirige vers HTTPS (curl -I http://domain → 301/308)
  □ Headers sécurité présents (X-Frame, HSTS, CSP)
  □ Ports: seuls 22/80/443 ouverts (nmap scan)

APPLICATION
  □ Auth fonctionne (register, login, refresh)
  □ Rate limiting actif (429 après dépassement limite)
  □ CORS restreint au domaine correct
  □ Endpoints sensibles protégés (401 sans token)
  □ Webhook signatures vérifiées

MONITORING
  □ Prometheus scrape toutes les métriques
  □ Alertmanager configuré (Telegram test reçu)
  □ Grafana accessible sur monitor.domain.ca

BACKUP
  □ Backup DB fonctionne (test manuel)
  □ Restauration testée

ACCÈS
  □ MFA activé sur GitHub
  □ SSH: clé uniquement (no password)
  □ Clé ed25519 dans authorized_keys
  □ Root login: prohibit-password
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 7. PLAYBOOKS D'INCIDENT
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🚨 INCIDENT-01: Clé API compromise (Stripe/OpenAI)
```
1. CONTENIR (< 5 min)
   → Stripe: Dashboard → API keys → Révoque la clé compromise
   → OpenAI: Platform → API keys → Delete
   
2. GÉNÉRER nouvelles clés immédiatement
   → Stripe: Create new secret key
   → OpenAI: Create new key
   
3. DÉPLOYER
   → ssh root@VPS
   → nano /opt/nanovia-os/.env
   → Remplacer les clés
   → docker compose restart api ai-orchestrator
   
4. INVESTIGUER
   → Vérifier logs Stripe: transactions suspectes?
   → Vérifier facture OpenAI: usage anormal?
   → git log --all --grep="env" → commit qui a exposé?
   
5. POST-MORTEM
   → Comment la clé a-t-elle été exposée?
   → Ajouter détection dans CI/CD
```

### 🚨 INCIDENT-02: VPS compromis / accès non autorisé
```
1. ISOLER (< 2 min)
   → OVH Manager → VPS → Éteindre le VPS
   → Changer mot de passe OVH Manager
   
2. ANALYSER (en rescue mode)
   → Monter disque → vérifier /var/log/auth.log
   → Vérifier crontabs: crontab -l + /etc/cron*
   → Vérifier processus suspects: ps aux
   → AIDE/rkhunter: comparer avec baseline
   
3. RESTAURER
   → Réinstaller VPS (option propre)
   → Restaurer DB depuis dernier backup propre
   → Redéployer depuis GitHub
   
4. POST-MORTEM
   → Vecteur d'entrée identifié?
   → Données compromises?
   → Notifier utilisateurs si nécessaire (RGPD: 72h)
```

### 🚨 INCIDENT-03: Perte base de données
```
1. NE PAS PANIQUER — backups existent
2. Identifier dernier backup valide: ls /opt/backups/postgres/
3. Restaurer:
   openssl enc -d -aes-256-cbc -pbkdf2 -k "$BACKUP_KEY" \
     -in backup.sql.gz.enc | gunzip | \
     docker exec -i infra-postgres-1 psql -U kt_user kt_monetization
4. Vérifier intégrité: SELECT COUNT(*) FROM users;
5. Redémarrer containers: docker compose restart api
```

### 🚨 INCIDENT-04: SSH bloqué (comme vécu!)
```
1. OVH Manager → VPS → Activer mode Rescue
2. Récupérer nouveau mot de passe rescue depuis email OVH
3. ssh root@167.114.155.166 (avec mot de passe rescue)
4. mount /dev/sdb1 /mnt/vps
5. # Ajouter la clé SSH publique de secours:
   echo "$EMERGENCY_SSH_PUBLIC_KEY" >> /mnt/vps/root/.ssh/authorized_keys
6. # Fix firewall si bloqué:
   chroot /mnt/vps systemctl disable nftables
   chroot /mnt/vps ufw allow 22
7. reboot
8. OVH Manager → Sortir du mode Rescue → Redémarrer normal
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 8. KPI SÉCURITÉ — TABLEAU DE BORD
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Métriques à suivre (revue mensuelle)

| KPI | Cible | Alerte si |
|---|---|---|
| MFA coverage | 100% comptes sensibles | < 100% |
| Vulnérabilités critiques (SAST) | 0 | > 0 en prod |
| Patch lag (security updates) | < 7 jours | > 14 jours |
| Backup success rate | 100% | < 100% |
| Backup restore tested | Mensuel | > 45 jours |
| Failed SSH attempts / jour | < 100 | > 500 |
| Uptime | > 99.5% | < 99% |
| SSL cert expiry | > 30 jours | < 14 jours |
| Secrets rotation age | < 90 jours | > 90 jours |
| Incidents non résolus | 0 | > 0 critique |

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 9. STANDARD SÉCURITÉ — NOUVEAU PROJET
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
### Template obligatoire pour chaque nouveau projet

```bash
# 1. Initialiser avec sécurité intégrée
git init mon-projet
cd mon-projet

# 2. .gitignore sécurité
cat >> .gitignore << 'EOF'
.env
.env.*
!.env.example
*.pem
*.key
secrets/
*.secret
EOF

# 3. .env.example (template sans valeurs réelles)
cat > .env.example << 'EOF'
DOMAIN=
SECRET_KEY=GENERATE_WITH_openssl_rand_hex_32
DATABASE_URL=
REDIS_URL=
STRIPE_SECRET_KEY=REPLACE_WITH_STRIPE_SECRET_KEY
OPENAI_API_KEY=REPLACE_WITH_OPENAI_API_KEY
EOF

# 4. Pre-commit hook (detect secrets)
pip install detect-secrets
detect-secrets scan > .secrets.baseline
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
EOF

# 5. GitHub Actions security pipeline
mkdir -p .github/workflows
# → Copier depuis nanovia-os/.github/workflows/sast.yml
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 10. CONTACTS & RESSOURCES
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```
URGENCES SÉCURITÉ
  OVH Support:    https://help.ovhcloud.com
  Stripe Security: security@stripe.com
  GitHub Security: security@github.com

OUTILS RÉFÉRENCE
  OWASP Top 10:  https://owasp.org/Top10
  CVE Database:  https://nvd.nist.gov
  HaveIBeenPwned: https://haveibeenpwned.com
  SSL Test:      https://www.ssllabs.com/ssltest
  Headers Test:  https://securityheaders.com

REVUES PÉRIODIQUES
  Hebdomadaire: vérifier alertes Grafana/Telegram
  Mensuel:      audit dépendances + test backup restore
  Trimestriel:  rotation secrets + revue accès + pentest
  Annuel:       révision politique sécurité complète
```

