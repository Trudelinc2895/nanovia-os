#!/usr/bin/env bash
# Create and verify the production snapshot required before an Alembic upgrade.
# PostgreSQL custom format is compressed but NOT encrypted. Protection at rest
# is provided by a dedicated directory (0700) and files restricted by umask 077.

set -Eeuo pipefail
umask 077

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_value() {
  local name="$1"
  [ -n "${!name:-}" ] || fail "Missing required value: ${name}"
}

validate_nonempty_file() {
  local path="$1"
  [ -f "${path}" ] && [ -s "${path}" ]
}

validate_checksum() {
  local checksum_path="$1"
  (
    cd "$(dirname "${checksum_path}")"
    sha256sum --check --status "$(basename "${checksum_path}")"
  )
}

run_pg_restore_list() {
  local dump_path="$1"
  compose exec -T postgres pg_restore --list < "${dump_path}" >/dev/null
}

validate_backup_artifacts() {
  local dump_path="$1"
  local dump_checksum_path="$2"
  local manifest_path="$3"
  local manifest_checksum_path="$4"

  validate_nonempty_file "${dump_path}" || return 1
  validate_nonempty_file "${manifest_path}" || return 1
  validate_checksum "${dump_checksum_path}" || return 1
  validate_checksum "${manifest_checksum_path}" || return 1
  run_pg_restore_list "${dump_path}" || return 1
}

self_test() {
  local test_dir
  local dump_path
  local dump_checksum_path
  local manifest_path
  local manifest_checksum_path
  local passed=0

  test_dir="$(mktemp -d)"
  dump_path="${test_dir}/database.dump"
  dump_checksum_path="${dump_path}.sha256"
  manifest_path="${test_dir}/manifest.txt"
  manifest_checksum_path="${manifest_path}.sha256"

  if validate_backup_artifacts \
    "${test_dir}/absent.dump" \
    "${dump_checksum_path}" \
    "${manifest_path}" \
    "${manifest_checksum_path}"; then
    fail "Self-test expected an absent backup to fail"
  fi
  passed=$((passed + 1))

  : > "${dump_path}"
  printf 'manifest\n' > "${manifest_path}"
  (
    cd "${test_dir}"
    sha256sum "$(basename "${dump_path}")" > "$(basename "${dump_checksum_path}")"
    sha256sum "$(basename "${manifest_path}")" > "$(basename "${manifest_checksum_path}")"
  )
  if validate_backup_artifacts \
    "${dump_path}" \
    "${dump_checksum_path}" \
    "${manifest_path}" \
    "${manifest_checksum_path}"; then
    fail "Self-test expected an empty dump to fail"
  fi
  passed=$((passed + 1))

  printf 'custom-dump-fixture\n' > "${dump_path}"
  (
    cd "${test_dir}"
    sha256sum "$(basename "${dump_path}")" > "$(basename "${dump_checksum_path}")"
  )
  printf 'corruption\n' >> "${dump_path}"
  if validate_backup_artifacts \
    "${dump_path}" \
    "${dump_checksum_path}" \
    "${manifest_path}" \
    "${manifest_checksum_path}"; then
    fail "Self-test expected a checksum mismatch to fail"
  fi
  passed=$((passed + 1))

  printf 'custom-dump-fixture\n' > "${dump_path}"
  (
    cd "${test_dir}"
    sha256sum "$(basename "${dump_path}")" > "$(basename "${dump_checksum_path}")"
  )
  run_pg_restore_list() { return 1; }
  if validate_backup_artifacts \
    "${dump_path}" \
    "${dump_checksum_path}" \
    "${manifest_path}" \
    "${manifest_checksum_path}"; then
    fail "Self-test expected pg_restore --list failure to fail"
  fi
  passed=$((passed + 1))

  run_pg_restore_list() { return 0; }
  validate_backup_artifacts \
    "${dump_path}" \
    "${dump_checksum_path}" \
    "${manifest_path}" \
    "${manifest_checksum_path}" \
    || fail "Self-test expected valid simulated artifacts to pass"
  passed=$((passed + 1))

  rm -f \
    "${dump_path}" \
    "${dump_checksum_path}" \
    "${manifest_path}" \
    "${manifest_checksum_path}"
  rmdir "${test_dir}"

  printf 'BACKUP_SELF_TESTS=%s\n' "${passed}"
  printf 'BACKUP_SELF_TEST_RESULT=PASS\n'
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit 0
fi

for name in \
  DEPLOY_PATH \
  COMPOSE_PROJECT_NAME \
  POSTGRES_VOLUME_NAME \
  REDIS_VOLUME_NAME \
  RUNTIME_ENV_FILE \
  BACKUP_ROOT \
  PREVIOUS_COMMIT \
  DEPLOY_SHA \
  CURRENT_ALEMBIC \
  EXPECTED_ALEMBIC_HEAD; do
  require_value "${name}"
done

case "${COMPOSE_PROJECT_NAME}" in
  nanovia-prod|nanovia-prod-*) fail "The non-canonical nanovia-prod project is forbidden" ;;
esac
case "${POSTGRES_VOLUME_NAME}:${REDIS_VOLUME_NAME}" in
  *nanovia-prod_*) fail "A non-canonical nanovia-prod volume is forbidden" ;;
esac

[ -d "${DEPLOY_PATH}/.git" ] || fail "DEPLOY_PATH is not a Git checkout"
[ -f "${RUNTIME_ENV_FILE}" ] || fail "Runtime environment file is absent"
[ -f "${DEPLOY_PATH}/infra/docker/Caddyfile" ] || fail "Canonical Caddyfile is absent"

REAL_DEPLOY_PATH="$(realpath "${DEPLOY_PATH}")"
install -d -m 700 "${BACKUP_ROOT}"
REAL_BACKUP_ROOT="$(realpath "${BACKUP_ROOT}")"
case "${REAL_BACKUP_ROOT}" in
  "${REAL_DEPLOY_PATH}"|"${REAL_DEPLOY_PATH}"/*)
    fail "BACKUP_ROOT must be outside the Git checkout"
    ;;
esac

cd "${REAL_DEPLOY_PATH}"
[ -z "$(git status --porcelain --untracked-files=all)" ] \
  || fail "Refusing to back up from a dirty checkout"
[ "$(git rev-parse HEAD)" = "${DEPLOY_SHA}" ] \
  || fail "Checkout does not match DEPLOY_SHA"

COMPOSE_FILES=(
  -f infra/docker-compose.prod.yml
  -f infra/docker-compose.canonical-prod.yml
)
compose() {
  APP_RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE}" \
    docker compose \
      -p "${COMPOSE_PROJECT_NAME}" \
      "${COMPOSE_FILES[@]}" \
      --env-file "${RUNTIME_ENV_FILE}" \
      "$@"
}

compose config --quiet

CANONICAL_VOLUMES=(
  "${POSTGRES_VOLUME_NAME}"
  "${REDIS_VOLUME_NAME}"
  "${COMPOSE_PROJECT_NAME}_caddy_data"
  "${COMPOSE_PROJECT_NAME}_caddy_config"
  "${COMPOSE_PROJECT_NAME}_grafana_data"
  "${COMPOSE_PROJECT_NAME}_prometheus_data"
  "${COMPOSE_PROJECT_NAME}_alertmanager_data"
)
for volume_name in "${CANONICAL_VOLUMES[@]}"; do
  docker volume inspect "${volume_name}" >/dev/null \
    || fail "Canonical external volume is absent"
done

UTC_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$(
  mktemp -d "${REAL_BACKUP_ROOT}/pre-migration-${UTC_TIMESTAMP}-XXXXXX"
)"
chmod 700 "${BACKUP_DIR}"

DUMP_PATH="${BACKUP_DIR}/postgres.dump"
DUMP_TEMP="${DUMP_PATH}.partial"
DUMP_CHECKSUM_PATH="${DUMP_PATH}.sha256"
MANIFEST_PATH="${BACKUP_DIR}/manifest.txt"
MANIFEST_CHECKSUM_PATH="${MANIFEST_PATH}.sha256"
GATE_PATH="${BACKUP_DIR}/backup.validated"

cleanup_partial_dump() {
  if [ -n "${DUMP_TEMP:-}" ] && [ -f "${DUMP_TEMP}" ]; then
    rm -f "${DUMP_TEMP}"
  fi
}
trap cleanup_partial_dump EXIT

# Copy without displaying or parsing the environment file.
install -m 600 "${RUNTIME_ENV_FILE}" "${BACKUP_DIR}/runtime.env"
install -m 600 \
  "${DEPLOY_PATH}/infra/docker/Caddyfile" \
  "${BACKUP_DIR}/Caddyfile"

compose exec -T postgres sh -ceu \
  'exec pg_dump --format=custom --compress=6 --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "${DUMP_TEMP}"
validate_nonempty_file "${DUMP_TEMP}" || fail "PostgreSQL dump is absent or empty"
mv "${DUMP_TEMP}" "${DUMP_PATH}"

(
  cd "${BACKUP_DIR}"
  sha256sum "$(basename "${DUMP_PATH}")" > "$(basename "${DUMP_CHECKSUM_PATH}")"
)

ACTIVE_CONTAINER_IDS=()
mapfile -t ACTIVE_CONTAINER_IDS < <(
  docker ps -aq --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}"
)
[ "${#ACTIVE_CONTAINER_IDS[@]}" -gt 0 ] || fail "No canonical containers found"

{
  printf 'format=nanovia-pre-migration-v1\n'
  printf 'created_utc=%s\n' "${UTC_TIMESTAMP}"
  printf 'previous_commit=%s\n' "${PREVIOUS_COMMIT}"
  printf 'deploy_commit=%s\n' "${DEPLOY_SHA}"
  printf 'alembic_current=%s\n' "${CURRENT_ALEMBIC}"
  printf 'alembic_expected_head=%s\n' "${EXPECTED_ALEMBIC_HEAD}"
  printf 'compose_project=%s\n' "${COMPOSE_PROJECT_NAME}"
  printf 'postgres_volume=%s\n' "${POSTGRES_VOLUME_NAME}"
  printf 'redis_volume=%s\n' "${REDIS_VOLUME_NAME}"
  printf 'dump_file=%s\n' "$(basename "${DUMP_PATH}")"
  printf 'dump_sha256=%s\n' "$(cut -d' ' -f1 "${DUMP_CHECKSUM_PATH}")"
  printf 'caddyfile_sha256=%s\n' "$(sha256sum "${BACKUP_DIR}/Caddyfile" | cut -d' ' -f1)"
  printf 'active_images_begin\n'
  for container_id in "${ACTIVE_CONTAINER_IDS[@]}"; do
    service="$(
      docker inspect \
        --format '{{index .Config.Labels "com.docker.compose.service"}}' \
        "${container_id}"
    )"
    image_id="$(docker inspect --format '{{.Image}}' "${container_id}")"
    image_ref="$(docker inspect --format '{{.Config.Image}}' "${container_id}")"
    container_state="$(docker inspect --format '{{.State.Status}}' "${container_id}")"
    image_digests="$(
      docker image inspect \
        --format '{{if .RepoDigests}}{{join .RepoDigests ","}}{{else}}none{{end}}' \
        "${image_id}"
    )"
    printf '%s|%s|%s|%s|%s\n' \
      "${service}" \
      "${container_state}" \
      "${image_id}" \
      "${image_ref}" \
      "${image_digests}"
  done
  printf 'active_images_end\n'
} > "${MANIFEST_PATH}"

validate_nonempty_file "${MANIFEST_PATH}" || fail "Backup manifest is absent or empty"
(
  cd "${BACKUP_DIR}"
  sha256sum "$(basename "${MANIFEST_PATH}")" > "$(basename "${MANIFEST_CHECKSUM_PATH}")"
)

validate_backup_artifacts \
  "${DUMP_PATH}" \
  "${DUMP_CHECKSUM_PATH}" \
  "${MANIFEST_PATH}" \
  "${MANIFEST_CHECKSUM_PATH}" \
  || fail "Backup validation failed"

{
  printf 'validated_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'deploy_commit=%s\n' "${DEPLOY_SHA}"
  printf 'dump_sha256=%s\n' "$(cut -d' ' -f1 "${DUMP_CHECKSUM_PATH}")"
  printf 'manifest_sha256=%s\n' "$(cut -d' ' -f1 "${MANIFEST_CHECKSUM_PATH}")"
} > "${GATE_PATH}"

validate_nonempty_file "${GATE_PATH}" || fail "Backup validation gate was not created"
chmod 600 "${BACKUP_DIR}"/*
trap - EXIT

printf 'VERIFIED_BACKUP_DIRECTORY=%s\n' "${BACKUP_DIR}"
printf 'VERIFIED_BACKUP_GATE=%s\n' "${GATE_PATH}"
