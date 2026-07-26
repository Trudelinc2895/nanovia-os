# J21A+ — Canonical production deployment

## Status and scope

This runbook prepares a future deployment. It does not authorize or perform a
deployment, a VPS write, a Stripe mutation, or a DNS change.

Canonical public runtime:

- checkout: `/opt/kt-monetization-os`
- Docker Compose project: `infra`
- approved J20 commit: `b85de68277c9f425f7dfe0e488f242c7d6942423`
- approved Alembic head: `c7e4a91f2b60`

The broken `/home/deploy/nanovia-os-production` checkout and its `nanovia-prod`
project are not deployment sources. No `nanovia-prod_*` volume may be used.

Stripe inventory note only:

- currently connected account: `acct_1TOCCXATTONMpA7y`
- expected J18 source account: `acct_1T2RAyPG4CQDEwTs`

These account IDs are not credentials. This procedure does not create, copy,
modify, or disable a Stripe object and does not invent any Stripe object ID.

## Required GitHub production configuration

The workflow fails closed when any required value is absent.

Environment variables:

| Name | Required production value |
| --- | --- |
| `DEPLOY_PATH` | `/opt/kt-monetization-os` |
| `COMPOSE_PROJECT_NAME` | `infra` |
| `POSTGRES_VOLUME_NAME` | Exact existing volume observed on the public PostgreSQL container |
| `REDIS_VOLUME_NAME` | Exact existing volume observed on the public Redis container |
| `RUNTIME_ENV_FILE` | Exact existing runtime env-file path; no fallback is applied |
| `BACKUP_ROOT` | Explicit absolute backup directory outside the Git checkout |

Environment secrets:

- `VPS_HOST`
- `VPS_SSH_PRIVATE_KEY`

The GitHub `production` environment must have required reviewers enabled before
the workflow is used. Referencing `environment: production` in YAML enables the
environment gate, but repository administrators must configure the reviewers.
That external configuration requires separate authorization.

The workflow input is a full lowercase 40-character commit SHA. A branch name,
tag, abbreviated SHA, or implicit latest commit is rejected.

## One reproducible preflight

Run only after explicit production authorization:

```bash
gh auth status --hostname github.com
git fetch origin
git cat-file -e "${DEPLOY_SHA}^{commit}"
git status --short --untracked-files=all
```

The production workflow then verifies over authenticated SSH, without printing
configuration values or env-file contents:

1. every required variable exists;
2. the deployment lock is available;
3. the checkout exists and its real path is exact;
4. the checkout is clean, including untracked files;
5. exactly one public Caddy container publishes port 80;
6. its Compose project and working-directory labels match the configured values;
7. the PostgreSQL and Redis volumes exist;
8. the active containers mount those exact volumes;
9. all other persistent volumes expected for the canonical project exist;
10. free disk space is at least 2 GiB plus twice the current database size;
11. the requested commit exists and is selected exactly;
12. the runtime env file exists, without reading or printing it;
13. the merged Compose configuration is valid;
14. active service and immutable image IDs are inventoried;
15. the current Alembic revision exists in the target migration history;
16. the target has the single approved head `c7e4a91f2b60`;
17. the custom-format PostgreSQL dump and manifest are both verified.

GitHub concurrency serializes workflow runs. A separate non-blocking `flock` on
the VPS rejects a concurrent manual or workflow deployment.

## Non-destructive reconciliation of the public checkout

The following four observed files must be handled individually:

1. `infra/docker/Caddyfile`
2. `infra/dns/DNS_RECORDS_TO_ADD.md`
3. `infra/docker/Caddyfile.backup-20260530-061752`
4. `infra/docker/Caddyfile.backup-20260530-061823`

Before changing any of them, create a dated archive outside the checkout. These
commands are prepared but have not been executed:

```bash
cd /opt/kt-monetization-os
RECONCILE_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
RECONCILE_DIR="/opt/nanovia-vps-reconciliation/${RECONCILE_UTC}"
install -d -m 700 "${RECONCILE_DIR}"

git status --short --untracked-files=all > "${RECONCILE_DIR}/git-status.txt"
git diff --binary -- infra/docker/Caddyfile > "${RECONCILE_DIR}/Caddyfile.patch"

sha256sum \
  infra/docker/Caddyfile \
  infra/dns/DNS_RECORDS_TO_ADD.md \
  infra/docker/Caddyfile.backup-20260530-061752 \
  infra/docker/Caddyfile.backup-20260530-061823 \
  > "${RECONCILE_DIR}/source-files.sha256"

tar -czf "${RECONCILE_DIR}/checkout-files.tar.gz" \
  infra/docker/Caddyfile \
  infra/dns/DNS_RECORDS_TO_ADD.md \
  infra/docker/Caddyfile.backup-20260530-061752 \
  infra/docker/Caddyfile.backup-20260530-061823

tar -tzf "${RECONCILE_DIR}/checkout-files.tar.gz" > "${RECONCILE_DIR}/archive-list.txt"
sha256sum "${RECONCILE_DIR}/checkout-files.tar.gz" \
  > "${RECONCILE_DIR}/checkout-files.tar.gz.sha256"
(
  cd "${RECONCILE_DIR}"
  sha256sum --check checkout-files.tar.gz.sha256
)
```

Create a classification record with one of these outcomes per file:

| Classification | Required action |
| --- | --- |
| Integrate | Reproduce the reviewed change locally in a separately authorized commit |
| Runtime only | Preserve it outside the checkout and document its runtime owner |
| Exclude | Move the exact file into the verified reconciliation directory |
| Uncertain | Stop; no checkout cleanup or deployment is allowed |

For the tracked Caddyfile, do not overwrite it. If its patch is classified as
excluded after review, the prepared reversible operation is to apply the saved
patch in reverse:

```bash
cd /opt/kt-monetization-os
git apply --check --reverse "${RECONCILE_DIR}/Caddyfile.patch"
git apply --reverse "${RECONCILE_DIR}/Caddyfile.patch"
```

This operation requires a separate VPS-write authorization. The three untracked
files may be moved by exact path into the verified reconciliation directory only
after classification. Nothing is deleted. A final `git status` must be empty.

## Canonical deployment sequence

The sole deployment entry point is:

```bash
gh workflow run .github/workflows/deploy.yml \
  --ref "${WORKFLOW_REF}" \
  -f deploy_sha="${DEPLOY_SHA}"
```

This command is not authorized by this document. When separately authorized,
the workflow performs:

1. GitHub environment approval;
2. exact-SHA checkout and GitHub authentication check;
3. authenticated SSH preflight;
4. project/path/volume reconciliation checks;
5. target image builds without replacing running containers;
6. target Alembic graph validation;
7. temporary stop of `api` and `ai-orchestrator` to freeze application writes;
8. verified custom-format PostgreSQL dump and manifest under that write freeze;
9. migration under the GitHub and VPS deployment locks;
10. confirmation that Alembic reached `c7e4a91f2b60`;
11. recreation of stateless application services only;
12. health, commit, revision, and restart-loop checks.

PostgreSQL and Redis are not recreated by the workflow. Existing external
volumes are neither created nor changed by Compose.

## Backup gate and manifest

`infra/scripts/pre-migration-backup.sh` creates:

- `postgres.dump`: PostgreSQL custom format, compressed, not encrypted;
- `postgres.dump.sha256`;
- protected copy of the runtime env file, never displayed;
- protected copy of the canonical Caddyfile;
- `manifest.txt`;
- `manifest.txt.sha256`;
- `backup.validated`, written only after all validation passes.

The manifest contains no password, API key, token, env-file content, email, or
customer data. It records:

- UTC timestamp;
- previous and requested commits;
- current and expected Alembic revisions;
- Compose project;
- PostgreSQL and Redis volume names;
- canonical services and their pre-deployment container states;
- container image IDs, configured image references, and available digests;
- dump and Caddyfile checksums.

The migration step refuses to run without the verified gate file.

## Postflight prepared for a future authorized deployment

Automated, non-PII checks:

- PostgreSQL health;
- Redis health;
- API container health;
- frontend container health;
- Caddy container state and public reverse-proxy response;
- canonical commit match;
- Alembic revision match;
- absence of restarting canonical containers.

Manual checks, to be performed without real payment or customer data:

```bash
curl --fail --silent --show-error https://nanovia.ca/api/v1/health
curl --fail --silent --show-error https://nanovia.ca/api/v1/health/ready
curl --fail --silent --show-error https://nanovia.ca/
curl --fail --silent --show-error https://nanovia.ca/pilot/confirmation
```

Additional controlled checks requiring a separate test protocol:

- load the Pilot form without submitting customer data;
- verify the generated Payment Link contains only `client_reference_id`;
- send a locally generated, correctly signed intentionally ignored webhook;
- confirm an invalid signature returns HTTP 400;
- query confirmation with an unknown synthetic session ID and confirm it never
  returns `confirmed`;
- inspect response keys to confirm no PII or internal Stripe identifier leaks.

A signed webhook test writes an audit event and therefore requires explicit
production-test authorization. A real payment, real email, Stripe object
mutation, or customer record must not be used.

## Reproducible rollback

### Failure before migration

- leave the database and volumes untouched;
- resume the previous `api` and `ai-orchestrator` containers if they were stopped;
- use the manifest to confirm their original image IDs;
- investigate before another workflow run.

### Failure during migration

- stop the deployment;
- preserve the verified dump, manifest, logs, and failed revision evidence;
- resume prior containers only if the schema remains backward compatible;
- do not run an automatic Alembic downgrade.

PostgreSQL transactional DDL reduces partial-migration risk, but it does not
justify assuming every future migration is reversible.

### Application rollback after a successful migration

1. verify whether any new Pilot request, payment, webhook, or sale was written;
2. if the schema is backward compatible, retag the recorded prior image IDs to
   their recorded image references;
3. select the recorded previous commit with `git switch --detach`;
4. validate Compose with the same project and external volumes;
5. recreate only the affected stateless services;
6. repeat health and revision checks.

The runtime env and Caddyfile snapshots may be restored by exact path only after
their checksums and destination are reviewed.

### Database restoration boundary

Database restoration is never automatic. It requires explicit approval and a
confirmed write freeze. After a new sale or Pilot write, restoring the old dump
would lose real data and is prohibited until those writes are reconciled.

## Explicitly forbidden operations

The deployment workflow and backup script must never execute:

- `git reset --hard`;
- `git clean`;
- `docker compose down -v`;
- `docker volume rm`;
- recursive deletion;
- a fallback to `nanovia-prod`;
- automatic `alembic downgrade`;
- replacement of the entire deployment directory.

## Local verification commands

These commands do not access the VPS or a real env file:

```bash
bash -n infra/scripts/pre-migration-backup.sh
bash infra/scripts/pre-migration-backup.sh --self-test
docker compose \
  -p infra \
  -f infra/docker-compose.prod.yml \
  -f infra/docker-compose.canonical-prod.yml \
  --env-file /path/to/generated-test-env \
  config --quiet
git diff --check -- \
  .github/workflows/deploy.yml \
  infra/docker-compose.prod.yml \
  infra/docker-compose.canonical-prod.yml \
  infra/scripts/pre-migration-backup.sh \
  docs/J21A_CANONICAL_DEPLOYMENT.md
```

The Docker Compose render validates configuration only. It does not prove that
PostgreSQL or Redis starts successfully when the local Docker daemon is stopped.
