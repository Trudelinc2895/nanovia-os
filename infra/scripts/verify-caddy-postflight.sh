#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_value() {
  local name="$1"
  [ -n "${!name:-}" ] || fail "Missing required value: ${name}"
}

require_non_negative_integer() {
  local name="$1"
  local value="${!name}"
  [[ "${value}" =~ ^[0-9]+$ ]] || fail "${name} must be a non-negative integer"
}

require_positive_integer() {
  local name="$1"
  require_non_negative_integer "${name}"
  [ "${!name}" -gt 0 ] || fail "${name} must be greater than zero"
}

COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-}"
RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE:-}"
PUBLIC_WEB_URL="${PUBLIC_WEB_URL:-}"
DOMAIN="${DOMAIN:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DOCKER_BIN="${DOCKER_BIN:-docker}"
CURL_BIN="${CURL_BIN:-curl}"
CADDY_POSTFLIGHT_ATTEMPTS="${CADDY_POSTFLIGHT_ATTEMPTS:-24}"
CADDY_POSTFLIGHT_DELAY_SECONDS="${CADDY_POSTFLIGHT_DELAY_SECONDS:-5}"
PUBLIC_POSTFLIGHT_ATTEMPTS="${PUBLIC_POSTFLIGHT_ATTEMPTS:-12}"
PUBLIC_POSTFLIGHT_DELAY_SECONDS="${PUBLIC_POSTFLIGHT_DELAY_SECONDS:-5}"
PUBLIC_CONNECT_TIMEOUT_SECONDS="${PUBLIC_CONNECT_TIMEOUT_SECONDS:-5}"
PUBLIC_MAX_TIME_SECONDS="${PUBLIC_MAX_TIME_SECONDS:-10}"

require_value COMPOSE_PROJECT_NAME
require_positive_integer CADDY_POSTFLIGHT_ATTEMPTS
require_non_negative_integer CADDY_POSTFLIGHT_DELAY_SECONDS
require_positive_integer PUBLIC_POSTFLIGHT_ATTEMPTS
require_non_negative_integer PUBLIC_POSTFLIGHT_DELAY_SECONDS
require_positive_integer PUBLIC_CONNECT_TIMEOUT_SECONDS
require_positive_integer PUBLIC_MAX_TIME_SECONDS
command -v "${DOCKER_BIN}" >/dev/null || fail "docker is required for the Caddy postflight"
command -v "${CURL_BIN}" >/dev/null || fail "curl is required for the public HTTPS postflight"
command -v "${PYTHON_BIN}" >/dev/null || fail "Python is required for the public HTTPS postflight"

if [ -z "${PUBLIC_WEB_URL}" ] || [ -z "${DOMAIN}" ]; then
  require_value RUNTIME_ENV_FILE
  [ -f "${RUNTIME_ENV_FILE}" ] || fail "Configured runtime environment file is absent"
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  VALIDATOR_PATH="${SCRIPT_DIR}/../../scripts/validate_runtime_env.py"
  [ -f "${VALIDATOR_PATH}" ] || fail "Canonical runtime environment validator is absent"
  read_runtime_value() {
    local key="$1"
    "${PYTHON_BIN}" - "${VALIDATOR_PATH}" "${RUNTIME_ENV_FILE}" "${key}" <<'PY'
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("validate_runtime_env", sys.argv[1])
if spec is None or spec.loader is None:
    raise SystemExit(1)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.load_env_file(Path(sys.argv[2])).get(sys.argv[3], "").strip())
PY
  }
  if [ -z "${PUBLIC_WEB_URL}" ]; then
    PUBLIC_WEB_URL="$(read_runtime_value PUBLIC_WEB_URL)"
  fi
  if [ -z "${DOMAIN}" ]; then
    DOMAIN="$(read_runtime_value DOMAIN)"
  fi
fi

require_value PUBLIC_WEB_URL
require_value DOMAIN
if ! "${PYTHON_BIN}" - "${PUBLIC_WEB_URL}" "${DOMAIN}" <<'PY'
from urllib.parse import urlsplit
import sys

raw_url, domain = sys.argv[1:]
try:
    url = urlsplit(raw_url)
    domain_url = urlsplit(f"//{domain}")
    url_port = url.port
    domain_port = domain_url.port
except ValueError:
    raise SystemExit(1)
domain_valid = (
    domain == domain.strip()
    and not any(character.isspace() for character in domain)
    and bool(domain_url.hostname)
    and domain_url.username is None
    and domain_url.password is None
    and domain_port is None
    and not domain_url.path
    and not domain_url.query
    and not domain_url.fragment
    and domain_url.hostname.lower() == domain.lower()
)
valid = (
    url.scheme == "https"
    and bool(url.hostname)
    and url.username is None
    and url.password is None
    and url_port in {None, 443}
    and not url.query
    and not url.fragment
    and not any(character.isspace() for character in raw_url)
    and domain_valid
    and url.hostname.lower() == domain.lower()
)
raise SystemExit(0 if valid else 1)
PY
then
  fail "PUBLIC_WEB_URL and DOMAIN must identify the same canonical HTTPS host"
fi

mapfile -t CADDY_IDS < <(
  "${DOCKER_BIN}" ps -a \
    --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" \
    --filter "label=com.docker.compose.service=caddy" \
    --format '{{.ID}}'
)
[ "${#CADDY_IDS[@]}" -eq 1 ] || fail "Unable to identify exactly one canonical Caddy container"
CADDY_ID="${CADDY_IDS[0]}"

stable_observations=0
required_stable_observations=2
if [ "${CADDY_POSTFLIGHT_ATTEMPTS}" -lt 2 ]; then
  required_stable_observations=1
fi

for ((attempt = 1; attempt <= CADDY_POSTFLIGHT_ATTEMPTS; attempt++)); do
  state="$(
    "${DOCKER_BIN}" inspect \
      --format '{{.State.Status}}|{{.State.Running}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "${CADDY_ID}" 2>/dev/null || true
  )"
  IFS='|' read -r container_status container_running container_health <<<"${state}"

  if [ "${container_health:-}" = "unhealthy" ]; then
    fail "Caddy reported an unhealthy container state"
  fi
  if [ "${container_status:-}" = "running" ] \
    && [ "${container_running:-}" = "true" ] \
    && { [ "${container_health:-}" = "healthy" ] || [ "${container_health:-}" = "none" ]; }; then
    stable_observations=$((stable_observations + 1))
    if [ "${stable_observations}" -ge "${required_stable_observations}" ]; then
      break
    fi
  else
    stable_observations=0
  fi

  if [ "${attempt}" -eq "${CADDY_POSTFLIGHT_ATTEMPTS}" ]; then
    fail "Caddy did not reach a stable running state within the bounded postflight"
  fi
  sleep "${CADDY_POSTFLIGHT_DELAY_SECONDS}"
done

validate_effective_url() {
  "${PYTHON_BIN}" - "$1" "${DOMAIN}" <<'PY'
from urllib.parse import urlsplit
import sys

raw_url, domain = sys.argv[1:]
try:
    url = urlsplit(raw_url)
    port = url.port
except ValueError:
    raise SystemExit(1)
valid = (
    url.scheme == "https"
    and bool(url.hostname)
    and url.username is None
    and url.password is None
    and port in {None, 443}
    and url.hostname.lower() == domain.lower()
)
raise SystemExit(0 if valid else 1)
PY
}

probe_https() {
  local target="$1"
  local label="$2"
  local attempt
  local effective_url
  for ((attempt = 1; attempt <= PUBLIC_POSTFLIGHT_ATTEMPTS; attempt++)); do
    if effective_url="$("${CURL_BIN}" \
      --fail \
      --silent \
      --show-error \
      --location \
      --proto '=https' \
      --proto-redir '=https' \
      --connect-timeout "${PUBLIC_CONNECT_TIMEOUT_SECONDS}" \
      --max-time "${PUBLIC_MAX_TIME_SECONDS}" \
      --output /dev/null \
      --write-out '%{url_effective}' \
      "${target}")" \
      && validate_effective_url "${effective_url}"; then
      return 0
    fi
    if [ "${attempt}" -lt "${PUBLIC_POSTFLIGHT_ATTEMPTS}" ]; then
      sleep "${PUBLIC_POSTFLIGHT_DELAY_SECONDS}"
    fi
  done
  fail "${label} failed within the bounded public HTTPS postflight"
}

PUBLIC_BASE_URL="${PUBLIC_WEB_URL%/}"
probe_https "${PUBLIC_BASE_URL}/api/v1/health/ready" "Public API readiness probe"
probe_https "${PUBLIC_BASE_URL}/" "Public entrypoint probe"

printf 'CADDY_POSTFLIGHT=verified\n'
