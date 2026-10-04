# Nanovia Pro Pilot — verification, 2026-10-04

Decision: NO-GO for production. Code corrections and staging synchronization are prepared; live provider/runtime evidence and dependency-security remediation are still required.

## Reference state

- PR46: `a9da24f3e02b3d090741283b1aefa04f604a5f24`, open, targeting main.
- PR49: `1552a83fdaf602574b1b56e388a27238d48ffe7c`, open, targeting integrate/nanovia-j21-main. It lacked the last three PR46 commits.
- No merge into main, production deployment, real charge, Stripe mutation, or VPS mutation was performed.

## Corrections and evidence

1. Added regressions that fail on the original PR46: a second unpaid Checkout later settles but remains unpaid locally; differing billing email permits a late unpaid event to regress the stored provider state; two clients behind Caddy share one rate bucket.
2. Retained `manual_review` while recording the newly verified paid state/event. Preserved paid/refunded/disputed states against old Checkout events, with no extra fulfillment. Existing atomicity/idempotence and refund tests remain green.
3. Rate limiting accepts exactly one validated forwarded IP only from the configured Caddy DNS peer. Direct callers, other containers, invalid/multiple headers and DNS failures cannot assert an identity. Uvicorn proxy-header rewriting is disabled so the TCP peer remains verifiable.
4. Canonical Caddy replaces X-Forwarded-For with its resolved client IP. Only the official Cloudflare peer ranges may supply CF-Connecting-IP (snapshot checked against https://www.cloudflare.com/ips-v4 and https://www.cloudflare.com/ips-v6 on 2026-10-04). Ranges must be rechecked during production preflight.
5. Combined PR49 with all three missing PR46 commits and both P1 corrections without conflicts.
6. Staging migration gate: validates runtime env, builds API with a SHA-specific staging image tag and SHA label, verifies label and exactly one Alembic head, verifies isolated staging DB volume, writes private custom-format dump/checksums/manifest, validates pg_restore listing, then upgrades the explicit head and verifies current revision. API is not rebuilt after the migration. Deployment is serialized.
7. CI/security PR triggers now include integrate/nanovia-j21-main, allowing PR49 to validate against its actual target. Push deployment conditions remain main/staging only.

## Executed verification

- Backend: `PYTHONPATH=backend python -m pytest backend/tests/ -q --tb=short` with real Docker Compose CLI available: **725 passed**, no skips, one upstream deprecation warning.
- Frontend: `npm ci`, `npm run build`: PASS (compile/types/static page generation).
- Frontend payment-link/confirmation: `node --test tests/*.test.mts`: **7 passed**.
- Staging gate: **10 executable simulated failure scenarios**, included in backend total. These are failure-order tests, not evidence of a real Docker build/database restore.
- Caddy **2.8.4**: canonical config adaptation PASS. Three local runtime proxy cases PASS using a trusted loopback peer fixture: independent visitors, spoofed XFF ignored, untrusted peer cannot supply CF-Connecting-IP. This does not attest the deployed Cloudflare configuration.
- Migration tests exercise J20 and d8f5b4c3a210 upgrade/downgrade and preservation of existing records on isolated **SQLite**. They do not prove PostgreSQL restoration or the VPS's migration graph.
- Production backup script self-tests: 5 PASS (simulated artifacts).
- Alertmanager renderer self-tests: 8 PASS, correct repository template supplied.
- Environment templates: 0 validation errors. No populated runtime env is available.
- Workflow YAML parse and git diff --check: PASS.
- Bandit HIGH/medium-confidence scan: 0 findings; report attached.

## Security reports — not a clean security verdict

- `pip-audit -r backend/requirements.txt`: nonzero; 123 report entries, **68 distinct package/advisory IDs across 7 packages**. Some entries are duplicate/disputed; exposure and upstream fixes need triage. See pip-audit-report.json.
- `npm audit --json`: nonzero; 10 affected package nodes (7 high, 2 moderate, 1 low). This includes development/transitive packages and is not a count of distinct exploitable production CVEs. See npm-audit.json.
- Existing CI reports several security scanners as non-blocking. A green workflow is not proof that these findings are absent or accepted.
- Do not apply `npm audit fix --force` blindly: suggested upgrades include major Tailwind/Next changes.

## Read-only external observations and access limits

- https://nanovia.ca responded HTTP 200 via Cloudflare.
- GET https://nanovia.ca/api/v1/health/ready responded HTTP 200 with postgres=ok and redis=ok. This does not identify the deployed commit, verify payment fulfillment, or attest the infrastructure behind it.
- Direct DNS resolution from this sandbox failed; HTTP used its configured egress path. Authoritative DNS/origin TLS remain unknown.
- Stripe connector returned UNAUTHORIZED/reauthentication required. No live or TEST account data was read. The historical nonconforming live contract remains unresolved until a fresh read.
- GitHub connector does not support production environment endpoints. Production variables, reviewer protection and secret presence remain unknown.
- No VPS SSH credential or approved host fingerprint is available in this workspace.
- Docker CLI/Compose rendering is available, but Docker daemon access is denied. Real PostgreSQL dump restoration, container migration and provider-network Stripe TEST end-to-end cannot be attested here.
- The staging workflow still uses ssh-keyscan to seed trust; independently verify the host fingerprint before executing it.

## Required next gates

1. Publish prepared PR branch changes and attach CI/review results to the resulting remote SHAs.
2. Triage dependency reports, apply supported minimal fixes, rerun affected checks; obtain independent GitHub approval.
3. Reconnect Stripe; read the specified Nanovia account and match 29700 CAD, Product, Price, Link, metadata, taxes, redirect, webhook and historical contracts. Live corrections require separate authorization.
4. Supply authorized staging runtime access through the credential manager, then execute real isolated PostgreSQL restore/migration/rollback and Stripe TEST funnel with recorded IDs and evidence.
5. Read production environment protections/configuration and VPS/Docker/volumes/DNS/TLS/Cloudflare/monitoring.
6. Stop for explicit authorization to merge main, verify resulting main CI, then stop for separate deployment authorization.
