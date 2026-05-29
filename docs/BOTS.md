# Bots Sandbox

Bots intégrés:

- `dashboard_bot`
- `automation_bot`
- `notification_bot`
- `stripe_test_bot`
- `module_test_bot`

## Endpoints

- `GET /bots`
- `POST /bots/{id}/run`

## Règles

- chaque bot passe par l'orchestrateur
- chaque exécution écrit dans l'audit log
- un bot n'exécute pas d'action destructive sans confirmation
- les bots peuvent être désactivés par la couche sandbox
