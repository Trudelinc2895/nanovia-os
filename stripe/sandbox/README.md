# Stripe Sandbox Assets

Ce dossier contient la source de vérité Stripe test pour Nanovia.

## Fichiers

- `products.json` : produits sandbox Starter / Pro / Business
- `prices.json` : prix mensuels sandbox
- `setup-stripe-sandbox.ps1` : charge `.env.sandbox` puis lance le bootstrap
- `stripe-output.sandbox.json` : IDs générés localement après bootstrap
- `webhook-test-events.md` : événements à couvrir côté backend

## Exécution

```powershell
cd C:\Users\Alienware\nanovia-os
powershell -ExecutionPolicy Bypass -File .\stripe\sandbox\setup-stripe-sandbox.ps1
```
