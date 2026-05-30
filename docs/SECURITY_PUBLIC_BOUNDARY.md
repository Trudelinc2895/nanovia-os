# Security Public Boundary

This repository is the public engineering workspace for Nanovia OS.

## Official system boundaries

- Stripe is the official source of truth for products, prices, subscriptions, invoices, and customer billing state.
- The Nanovia backend is the source of truth for access control, entitlements, quotas, OpenAI usage tracking, and profit calculations.
- The billing dashboard is a visual layer that reads Stripe billing data plus backend usage and profitability data.

## What belongs in the public repo

- generic application code
- generic types and interfaces
- non-sensitive helpers
- neutral documentation
- `.env.example` files without real values
- validation and deployment scripts without secrets

## What does not belong in the public repo

- business strategy details
- private module pricing strategy
- secrets or API keys
- webhook signing secrets
- database credentials
- internal profit mappings
- generated Stripe output files
- environment files with real values

## Private locations

Detailed commercial strategy, real environment values, private Stripe setup outputs, and production secrets must remain in private infrastructure such as:

- private local workspace
- secrets vaults
- VPS environment files with restricted access

This boundary keeps the public repository reusable and auditable without exposing commercial leverage or operational secrets.
