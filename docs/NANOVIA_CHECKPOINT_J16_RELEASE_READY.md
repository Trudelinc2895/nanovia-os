# Nanovia J16 — Release readiness

Date: 2026-07-19

## Portée

- Offre unique Nanovia Pro Pilot: 297 CAD pour 30 jours.
- Suivi optionnel: 79 CAD par mois, sans activation automatique.
- Tunnel public, onboarding, inscription, conditions et métadonnées alignés.
- Lien public Stripe centralisé et surchargeable par
  `NEXT_PUBLIC_PRO_PILOT_PAYMENT_URL`.
- Aucun changement Stripe Live, DNS, VPS ou production.

## Preuves locales

- `npm ci`: réussi.
- `npm run lint`: réussi, zéro avertissement.
- `npm run build`: réussi avec Next.js 16.2.10, 26 routes générées.
- `npm audit --audit-level=high`: zéro vulnérabilité.
- `python -m pytest tests/ -q --tb=short`: 165 tests réussis.
- `git diff --check`: réussi.
- Scan ciblé des secrets dans le diff: aucun secret détecté.

Docker n'était pas disponible dans l'environnement local. La construction et
le scan des images restent donc une preuve attendue de la CI GitHub.

## Déploiement préparé

1. Fusionner la PR J16 dans `main` seulement après CI verte et approbation.
2. Utiliser le workflow `Deploy — OVH staging/production` avec l'environnement
   `production`; le workflow refuse un checkout VPS sale ou des secrets absents.
3. Vérifier après déploiement:
   - `https://nanovia.ca` et `https://www.nanovia.ca`;
   - `/contact`, `/register` et le lien Stripe;
   - `/api/v1/health/ready`;
   - absence de réponses 502/525;
   - isolation de `admin.nanovia.ca`.

## Rollback préparé

En cas d'échec, redéployer le commit `main` immédiatement antérieur à la fusion
J16 avec le même workflow et les mêmes contrôles de santé. Ne jamais modifier
les données Stripe ni la base pour effectuer ce rollback frontend.
