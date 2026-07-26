# NANOVIA CHECKPOINT J13A2 COMMIT SCOPE

## Protection des modules

- Pro Pilot = tunnel de lancement
- Modules = actifs long terme conserves
- Aucun module supprime
- Aucun dossier module supprime
- Aucun fichier module supprime
- Les elements hors release restent disponibles pour une phase future
- Le commit doit etre minimal et non destructif

## Regle de classement

- **A** = necessaire pour la release publique Nanovia Pro Pilot
- **B** = checkpoints / documentation utiles a conserver
- **C** = hors-scope pour ce commit, **a conserver mais a ne pas inclure**

## A) Necessaires pour release Nanovia Pro Pilot

- `frontend/client/app/page.tsx`
- `frontend/client/app/contact/page.tsx`
- `frontend/client/app/demo-pilot-section.tsx`

## B) Checkpoints / documentation utiles

- `NANOVIA_CHECKPOINT_J7.md`
- `NANOVIA_CHECKPOINT_J7_LIVE.md`
- `NANOVIA_CHECKPOINT_J8_DEMO.md`
- `NANOVIA_CHECKPOINT_J9_EXEMPLES.md`
- `NANOVIA_CHECKPOINT_J10_PUBLIC_AUDIT.md`
- `NANOVIA_CHECKPOINT_J11_DEPLOY_PLAN.md`
- `NANOVIA_CHECKPOINT_J12_PREFLIGHT_DEPLOY.md`
- `NANOVIA_CHECKPOINT_J13A_RELEASE_REVIEW.md`
- `NANOVIA_LAUNCH_LOCK.md`
- `NANOVIA_REPO_ROLES.md`
- `ce_qui_bloque.md`
- `ce_qui_est_vendable.md`
- `ce_qui_marche.md`
- `docs/NANOVIA_MIGRATION_PLAN.md`
- `docs/PHASE_4A_IMPLEMENTATION_CHECKLIST.md`
- `docs/PRODUCTION_OPS.md`
- `docs/STRIPE_ENTITLEMENTS.md`
- `docs/TENANCY.md`
- `docs/UI_UX_NANOVIA.md`

## C) Hors-scope a exclure du commit de lancement, mais a conserver

- `frontend/client/app/layout.tsx`
- `frontend/client/app/register/page.tsx`

## Decision release

- Le commit de lancement ne doit publier que le tunnel **Nanovia Pro Pilot**
- Les modules existants ne sont ni remplaces, ni fusionnes agressivement, ni supprimes
- Tout element hors-scope reste disponible pour une phase future

## git status --short complet

```text
A  docs/NANOVIA_MIGRATION_PLAN.md
A  docs/PHASE_4A_IMPLEMENTATION_CHECKLIST.md
A  docs/PRODUCTION_OPS.md
A  docs/STRIPE_ENTITLEMENTS.md
A  docs/TENANCY.md
A  docs/UI_UX_NANOVIA.md
 M frontend/client/app/contact/page.tsx
 M frontend/client/app/layout.tsx
 M frontend/client/app/page.tsx
 M frontend/client/app/register/page.tsx
?? NANOVIA_CHECKPOINT_J10_PUBLIC_AUDIT.md
?? NANOVIA_CHECKPOINT_J11_DEPLOY_PLAN.md
?? NANOVIA_CHECKPOINT_J12_PREFLIGHT_DEPLOY.md
?? NANOVIA_CHECKPOINT_J13A2_COMMIT_SCOPE.md
?? NANOVIA_CHECKPOINT_J13A_RELEASE_REVIEW.md
?? NANOVIA_CHECKPOINT_J7.md
?? NANOVIA_CHECKPOINT_J7_LIVE.md
?? NANOVIA_CHECKPOINT_J8_DEMO.md
?? NANOVIA_CHECKPOINT_J9_EXEMPLES.md
?? NANOVIA_LAUNCH_LOCK.md
?? NANOVIA_REPO_ROLES.md
?? ce_qui_bloque.md
?? ce_qui_est_vendable.md
?? ce_qui_marche.md
?? frontend/client/app/demo-pilot-section.tsx
```

## git diff --name-only complet

```text
frontend/client/app/contact/page.tsx
frontend/client/app/layout.tsx
frontend/client/app/page.tsx
frontend/client/app/register/page.tsx
```

## Verification explicite avant commit

- aucun `.env` dans les fichiers modifies / non suivis listes ci-dessus
- aucun lien `buy.stripe.com/test_` detecte dans `frontend/client`
- lien LIVE confirme :
  - `https://buy.stripe.com/eVqaEZ2vF03j0De6bC1ZS02`
- email public confirme :
  - `nanovia@duck.com`
- `/contact` existe toujours dans le tunnel local
- aucun email public detecte pour :
  - `admin@tkverse.ca`
  - `admin@nanovia.ca`
  - `trudelinc@gmail.com`
  - `trudelinc11@gmail.com`

## Tableau exact A / B / C

| Fichier | Statut | Categorie | Justification |
| --- | --- | --- | --- |
| `frontend/client/app/page.tsx` | `M` | A | Home publique Pro Pilot, Stripe LIVE, exemples et tunnel de lancement. |
| `frontend/client/app/contact/page.tsx` | `M` | A | Onboarding `/contact` Pro Pilot avec email public `nanovia@duck.com`. |
| `frontend/client/app/demo-pilot-section.tsx` | `??` | A | Composant demo locale necessaire a la page publique Pro Pilot. |
| `frontend/client/app/layout.tsx` | `M` | C | Ajustement global de style, non indispensable au commit minimal de lancement. |
| `frontend/client/app/register/page.tsx` | `M` | C | Changement de wording inscription, hors tunnel public Pro Pilot minimal. |
| `NANOVIA_CHECKPOINT_J8_DEMO.md` | `??` | B | Trace de validation utile, pas necessaire pour publier la home. |
| `NANOVIA_CHECKPOINT_J9_EXEMPLES.md` | `??` | B | Trace de validation utile des exemples vendables. |
| `NANOVIA_CHECKPOINT_J10_PUBLIC_AUDIT.md` | `??` | B | Audit public utile avant deploiement, optionnel au commit. |
| `NANOVIA_CHECKPOINT_J11_DEPLOY_PLAN.md` | `??` | B | Documentation utile du plan de deploiement. |
| `NANOVIA_CHECKPOINT_J12_PREFLIGHT_DEPLOY.md` | `??` | B | Documentation utile du pre-vol. |
| `NANOVIA_CHECKPOINT_J13A_RELEASE_REVIEW.md` | `??` | B | Documentation utile de revue release. |
| `NANOVIA_CHECKPOINT_J13A2_COMMIT_SCOPE.md` | `??` | B | Documentation utile du perimetre de commit et protection modules. |
| `NANOVIA_CHECKPOINT_J7.md` | `??` | B | Historique de checkpoint utile, pas requis pour le tunnel. |
| `NANOVIA_CHECKPOINT_J7_LIVE.md` | `??` | B | Historique de checkpoint utile, pas requis pour le tunnel. |
| `NANOVIA_LAUNCH_LOCK.md` | `??` | B | Documentation de cadrage lancement, optionnelle au commit. |
| `NANOVIA_REPO_ROLES.md` | `??` | B | Documentation de repo utile, hors besoin technique du tunnel. |
| `ce_qui_bloque.md` | `??` | B | Notes utiles de suivi, non necessaires a la release publique. |
| `ce_qui_est_vendable.md` | `??` | B | Notes utiles sur l'offre, non necessaires techniquement. |
| `ce_qui_marche.md` | `??` | B | Notes utiles de suivi, non necessaires techniquement. |
| `docs/NANOVIA_MIGRATION_PLAN.md` | `A` | C | Documentation large hors tunnel public immediat, a conserver. |
| `docs/PHASE_4A_IMPLEMENTATION_CHECKLIST.md` | `A` | C | Documentation infra/processus hors commit de lancement. |
| `docs/PRODUCTION_OPS.md` | `A` | C | Documentation ops, utile mais hors release publique immediate. |
| `docs/STRIPE_ENTITLEMENTS.md` | `A` | C | Documentation billing/modulaire, a conserver hors commit minimal. |
| `docs/TENANCY.md` | `A` | C | Documentation architecture hors tunnel de lancement. |
| `docs/UI_UX_NANOVIA.md` | `A` | C | Documentation design large, pas necessaire au commit minimal. |

## Commandes git add proposees mais NON executees

### Option minimale recommandee

```bash
git add frontend/client/app/page.tsx frontend/client/app/contact/page.tsx frontend/client/app/demo-pilot-section.tsx
```

### Option avec checkpoints utiles

```bash
git add frontend/client/app/page.tsx frontend/client/app/contact/page.tsx frontend/client/app/demo-pilot-section.tsx NANOVIA_CHECKPOINT_J8_DEMO.md NANOVIA_CHECKPOINT_J9_EXEMPLES.md NANOVIA_CHECKPOINT_J10_PUBLIC_AUDIT.md NANOVIA_CHECKPOINT_J11_DEPLOY_PLAN.md NANOVIA_CHECKPOINT_J12_PREFLIGHT_DEPLOY.md NANOVIA_CHECKPOINT_J13A_RELEASE_REVIEW.md NANOVIA_CHECKPOINT_J13A2_COMMIT_SCOPE.md
```

## Message de commit propose

- `feat(frontend): publish Nanovia Pro Pilot launch funnel`

## Decision

- **Pret pour revue humaine du perimetre — aucun commit execute.**
