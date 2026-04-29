# NEXT STEPS — Nanovia OS
## Mis à jour : 2026-04-27

Les étapes sont ordonnées par impact/urgence. Attaquer une à la fois.

---

## 🔴 ÉTAPE 1 — Renseigner les vraies clés et price IDs (indispensable avant usage réel)

**Pourquoi :** Le code et la stack sont prêts, mais Stripe/Resend restent dépendants de vraies valeurs externes.

```powershell
cd C:\Users\Alienware\kt-monetization-os
Copy-Item infra\env\.env.dev.example .env.dev
# Remplir ensuite dans .env.dev :
# - STRIPE_SECRET_KEY / STRIPE_PUBLIC_KEY / STRIPE_WEBHOOK_SECRET
# - STRIPE_PRICE_*
# - RESEND_API_KEY si emails réels voulus
```

---

## 🔴 ÉTAPE 2 — Générer ou synchroniser le catalogue Stripe

**Pourquoi :** Les abonnements mensuels/annuels et packs dépendent des `price_id` réellement présents dans Stripe.

```powershell
cd C:\Users\Alienware\kt-monetization-os
python stripe\setup_stripe.py
```

**À faire ensuite :**
- Copier les `STRIPE_PRICE_*` générés dans `.env.dev`, `.env.staging` ou `.env.production`
- Garder `sk_test_` en dev/staging et `sk_live_` uniquement en prod

---

## 🟡 ÉTAPE 3 — Démarrer la stack locale recommandée

**Pourquoi :** C'est désormais le chemin de dev propre et reproductible.

```powershell
cd C:\Users\Alienware\kt-monetization-os
docker compose --env-file .env.dev -f infra\docker-compose.dev.yml up --build
```

**Endpoints attendus :**
- Web: `http://localhost:3000`
- API: `http://127.0.0.1:8010`
- Docs: `http://127.0.0.1:8010/docs`

---

## 🟡 ÉTAPE 4 — Tester le flow Stripe end-to-end

**Pourquoi :** Le code est présent, mais il faut confirmer la vraie intégration avec des clés valides.

```powershell
# Terminal 1
docker compose --env-file .env.dev -f infra\docker-compose.dev.yml up --build

# Terminal 2
stripe listen --forward-to localhost:8010/api/v1/billing/webhook

# Terminal 3
stripe trigger checkout.session.completed
```

---

## 🟡 ÉTAPE 5 — Décider du futur du service `frontend/admin`

**Pourquoi :** L'UI admin réelle vit dans `frontend/client/app/admin`, alors que `frontend/admin` reste un stub de déploiement.

---

## 🟢 ÉTAPE 6 — Remplacer les métriques placeholder du mobile

**Pourquoi :** C'est le dernier point technique encore explicitement documenté comme incomplet dans le code applicatif.

---

## Pour chaque nouvelle session

1. Démarrer par `.env.dev` + `infra/docker-compose.dev.yml`
2. Vérifier si la session a besoin de vraies intégrations externes ou seulement d'un run local
3. Ne pas supposer que `frontend/admin` est la vraie surface admin
4. Mettre à jour `KNOWN_BUGS.md` et ce fichier dès qu'un point change réellement
