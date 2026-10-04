#!/usr/bin/env bash
# Staging only: build the selected tree, prove its single head, then snapshot
# the database before invoking Alembic. Never restore/downgrade automatically.
set -Eeuo pipefail
umask 077
: "${TARGET_ENV:?}" "${TARGET_SHA:?}" "${DEPLOY_PATH:?}"
[ "${TARGET_ENV}" = staging ] || { echo 'ERROR: staging only' >&2; exit 1; }
cd "${DEPLOY_PATH}"
[ "$(git rev-parse HEAD)" = "${TARGET_SHA}" ]
[ -z "$(git status --porcelain --untracked-files=all)" ]
export STAGING_DEPLOY_SHA="${TARGET_SHA}"
IMAGE_REF="nanovia-api-staging:${TARGET_SHA}"
COMPOSE_ARGS=(
  -p nanovia-staging
  -f infra/docker-compose.prod.yml
  -f infra/docker-compose.staging.yml
  --env-file .env.staging
)
compose() { docker compose "${COMPOSE_ARGS[@]}" "$@"; }
python3 scripts/validate_runtime_env.py --env-file .env.staging --target-env staging
compose config --quiet
compose build --build-arg "DEPLOY_SHA=${TARGET_SHA}" api
IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${IMAGE_REF}")"
[ -n "${IMAGE_ID}" ] || { echo 'ERROR: missing built API image' >&2; exit 1; }
[ "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "${IMAGE_ID}")" = "${TARGET_SHA}" ]
EXPECTED_ALEMBIC_HEAD=d8f5b4c3a210
HEADS="$(compose run --rm --no-deps api python -m alembic heads)"
[ "${HEADS}" = "${EXPECTED_ALEMBIC_HEAD} (head)" ] \
  || { echo 'ERROR: unexpected or multiple Alembic heads' >&2; exit 1; }

# The fixed staging project uses its own named database volume, never prod.
DB_ID="$(compose ps -q postgres)"
[ -n "${DB_ID}" ]
DB_VOLUME="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "${DB_ID}")"
[ "${DB_VOLUME}" = nanovia-staging_postgres_data ] \
  || { echo 'ERROR: database is not on the isolated staging volume' >&2; exit 1; }
BACKUP_ROOT="$(dirname "$(pwd -P)")/.nanovia-staging-backups"
[ ! -L "${BACKUP_ROOT}" ]
install -d -m 700 "${BACKUP_ROOT}"
BACKUP_DIR="$(mktemp -d "${BACKUP_ROOT}/pre-migration-XXXXXXXX")"
compose exec -T postgres sh -ceu \
  'exec pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "${BACKUP_DIR}/postgres.dump"
test -s "${BACKUP_DIR}/postgres.dump"
(cd "${BACKUP_DIR}" && sha256sum postgres.dump > postgres.dump.sha256 && sha256sum --check --status postgres.dump.sha256)
compose exec -T postgres pg_restore --list < "${BACKUP_DIR}/postgres.dump" > /dev/null
CURRENT="$(compose run --rm --no-deps api python -m alembic current)"
printf 'commit=%s\nimage=%s\ncurrent=%s\nhead=%s\nvolume=%s\n' \
  "${TARGET_SHA}" "${IMAGE_ID}" "${CURRENT}" "${EXPECTED_ALEMBIC_HEAD}" "${DB_VOLUME}" > "${BACKUP_DIR}/manifest.txt"
(cd "${BACKUP_DIR}" && sha256sum manifest.txt > manifest.txt.sha256)
# Recheck the build context and image immediately before the write.
[ -z "$(git status --porcelain --untracked-files=all)" ]
[ "$(docker image inspect --format '{{.Id}}' "${IMAGE_REF}")" = "${IMAGE_ID}" ]
compose run --rm --no-deps api python -m alembic upgrade "${EXPECTED_ALEMBIC_HEAD}"
CURRENT="$(compose run --rm --no-deps api python -m alembic current)"
[ "${CURRENT}" = "${EXPECTED_ALEMBIC_HEAD} (head)" ]
printf 'STAGING_MIGRATION=PASS\nVERIFIED_BACKUP_DIRECTORY=%s\n' "${BACKUP_DIR}"
