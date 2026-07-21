# NANOVIA CHECKPOINT J16 - PRO PILOT FUNNEL

Date: 2026-07-21

## Périmètre confirmé

- Produit unique : Nanovia Pro Pilot
- Offre : automatisation assistée d'une tâche répétitive en 30 jours
- Prix : 297 CAD
- Suivi optionnel : 79 CAD / mois
- Branche : `feat/nanovia-architecture-uiux-tenancy-v3`
- Point de départ : `23ceb9c`

## Corrections locales

- CTA publics guidés vers la qualification avant le paiement.
- Formulaire Pilot branché sur `POST /api/v1/contact`.
- Confirmation affichée uniquement après acceptation de l'envoi par Resend.
- Secours courriel explicite si la transmission API échoue.
- Champs utilisateur échappés avant insertion dans l'email HTML.
- Adresse IP retirée du contenu envoyé par email.
- Métadonnées, conditions et confidentialité alignées sur l'offre Pilot.
- Build bloqué par ESLint remis au vert.

## Vérifications exécutées

- `npm.cmd run lint` : OK, aucun avertissement ni erreur.
- `npm.cmd run build` : OK, 27 pages générées.
- `python -m pytest tests/test_contact.py -q` : 2 tests passés.
- Test auth représentatif isolé : passé.
- Routes locales `/`, `/contact`, `/terms`, `/privacy` : HTTP 200 et contenu attendu présent.
- Lien Stripe public : HTTP 200; présence de `297` et `CAD` confirmée dans le HTML public.

## Limites et blocages réels

- Aucun déploiement ni changement Stripe, DNS ou infrastructure effectué.
- Le nom exact du produit et la redirection après paiement du Payment Link Stripe ne sont pas confirmés.
- La configuration production de Resend et l'adresse destinataire ne sont pas confirmées en runtime.
- L'identité commerciale complète, les coordonnées obligatoires, la politique d'annulation/remboursement et la transmission du contrat doivent être validées avant vente à distance.
- La suite backend groupée conserve un problème d'isolation d'état/environnement; un test auth isolé passe.
- Vérification visuelle interactive indisponible dans cette session; build et rendu HTTP validés.

## Prochaine action recommandée

Effectuer un preflight final sans mutation : vérifier dans Stripe le nom du produit, le montant total/taxes, la redirection post-paiement et la confirmation client; vérifier Resend en staging/test; compléter les informations légales manquantes. Présenter ensuite le diagnostic final avant tout déploiement.

## Continuation J16 - stabilité backend

Diagnostic confirmé :

- La configuration de test dépendait de l'ordre de collecte Pytest.
- `conftest.py` utilisait `setdefault`, ce qui laissait fuiter `APP_ENV=staging` et des identifiants fournisseurs depuis l'environnement hôte.
- Le test auth redéfinissait ensuite les variables trop tard, après l'instanciation du singleton `settings`.
- Le test de rate limit dépendait de la charge CPU/mémoire réelle et devenait non déterministe.
- L'alias legacy `SCRAPE_TIMEOUT_MS` était converti par un validateur mais éliminé par Pydantic avant d'atteindre ce validateur.

Corrections :

- Environnement Pytest centralisé et forcé avant toute collecte applicative.
- Identifiants Resend, OpenAI, Telegram et Stripe neutralisés dans les tests.
- Redis de test dirigé vers un port loopback fermé pour un échec immédiat sans réseau.
- Multiplicateur adaptatif fixé uniquement dans le scénario qui vérifie la limite nominale.
- Quatre tests séparés ajoutés pour couvrir les multiplicateurs adaptatifs.
- Alias `SCRAPE_TIMEOUT_MS` déclaré et converti vers `SCRAPING_TIMEOUT_SECONDS`.

Résultats finaux :

- Groupe contact + auth : 21 tests passés, 0 échec.
- Suite backend complète : 169 tests passés, 0 échec, 3 avertissements de dépréciation asyncio Windows.
- Aucun déploiement, commit, push ou changement d'infrastructure externe.
