# Production Hardening Checklist

This repository is already on **Next.js 15.5.15** in `frontend/client/package.json`, so the previously reported `14.2.3` version is not the current blocker.

## Framework and dependency baseline

- Keep Next.js on a current stable release line
- Rebuild the frontend lockfile in CI after dependency upgrades
- Review security advisories before every production rollout

## Edge and network protection

- Put **Cloudflare** in front of `nanovia.ca`
- Enable **WAF** and bot protection rules
- Force **HTTPS** only
- Keep DNS, TLS, firewall, and origin exposure aligned before go-live
- Restrict private/admin surfaces by IP allowlist

## Application protections

- Security headers must stay enabled:
  - CSP
  - HSTS
  - X-Frame-Options
  - Referrer-Policy
- Rate limiting must cover:
  - login and password recovery
  - contact form
  - billing checkout and portal routes
- Secrets must stay in environment variables or a secrets manager, never in source control

## Stripe production readiness

- Stripe stays on Billing APIs + Checkout Sessions for subscriptions
- Use live keys only in production runtime config
- Prefer restricted API keys where possible
- Webhook signature verification is mandatory
- Validate live webhooks, live price IDs, receipts, bank payouts, and tax settings before go-live
- Do not hardcode `payment_method_types` in Checkout Sessions

## Operations

- Enable automatic security updates on the VPS
- Enable automated encrypted backups
- Keep Prometheus, Alertmanager, and Grafana configured with real notification targets
- Test restore procedures, not only backup creation

## Access control

- Enable 2FA or passkeys on:
  - OVH
  - GitHub
  - Stripe
  - Vercel or any frontend hosting platform

## External go-live blockers to validate before deployment

- `nanovia.ca` resolves correctly in DNS
- TLS certificates issue successfully
- origin server is reachable only through the intended path
- Stripe is switched from test to live with verified webhook delivery
- production secrets are present on the VPS or secrets backend
