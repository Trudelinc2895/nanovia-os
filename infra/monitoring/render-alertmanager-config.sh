#!/bin/sh
set -eu

umask 077

readonly TEMPLATE_PATH="/etc/alertmanager/alertmanager.yml.tmpl"
readonly RUNTIME_DIR="/tmp/alertmanager-runtime"
readonly RUNTIME_CONFIG="${RUNTIME_DIR}/alertmanager.yml"
readonly TOKEN_FILE="${RUNTIME_DIR}/telegram_bot_token"
readonly AMTOOL_BIN="/bin/amtool"
readonly ALERTMANAGER_BIN="/bin/alertmanager"

fail() {
  printf 'alertmanager-render: %s\n' "$1" >&2
  exit 1
}

validate_inputs() {
  test "${TELEGRAM_BOT_TOKEN+x}" = "x" \
    || fail "TELEGRAM_BOT_TOKEN is required"
  test -n "${TELEGRAM_BOT_TOKEN}" \
    || fail "TELEGRAM_BOT_TOKEN must not be empty"
  test "${TELEGRAM_CHAT_ID+x}" = "x" \
    || fail "TELEGRAM_CHAT_ID is required"
  printf '%s\n' "${TELEGRAM_CHAT_ID}" \
    | LC_ALL=C grep -Eq '^-?[1-9][0-9]*$' \
    || fail "TELEGRAM_CHAT_ID must be a signed non-zero integer"
}

prepare_runtime_dir() {
  runtime_dir="$1"
  runtime_config="$2"
  token_file="$3"

  if test -e "${runtime_dir}" || test -L "${runtime_dir}"; then
    test -d "${runtime_dir}" && test ! -L "${runtime_dir}" \
      || fail "runtime path must be a real directory"
    rm -f -- "${runtime_config}" "${token_file}"
  else
    mkdir -p -- "${runtime_dir}"
  fi

  chmod 700 -- "${runtime_dir}"
}

render_config() {
  template_path="$1"
  runtime_dir="$2"
  runtime_config="$3"
  token_file="$4"

  validate_inputs
  test -f "${template_path}" && test ! -L "${template_path}" \
    || fail "Alertmanager template is missing or unsafe"

  prepare_runtime_dir "${runtime_dir}" "${runtime_config}" "${token_file}"

  printf '%s' "${TELEGRAM_BOT_TOKEN}" > "${token_file}"
  chmod 600 -- "${token_file}"

  ALERTMANAGER_TELEGRAM_BOT_TOKEN_FILE="${token_file}"
  export ALERTMANAGER_TELEGRAM_BOT_TOKEN_FILE
  LC_ALL=C awk '
    {
      gsub(/\$\{ALERTMANAGER_TELEGRAM_BOT_TOKEN_FILE\}/,
           ENVIRON["ALERTMANAGER_TELEGRAM_BOT_TOKEN_FILE"])
      gsub(/\$\{TELEGRAM_CHAT_ID\}/, ENVIRON["TELEGRAM_CHAT_ID"])
      print
    }
  ' "${template_path}" > "${runtime_config}"
  chmod 600 -- "${runtime_config}"

  if LC_ALL=C grep -Eq '\$\{[^}]+\}' "${runtime_config}"; then
    fail "rendered configuration contains an unresolved placeholder"
  fi
  LC_ALL=C grep -Eq \
    '^[[:space:]]*chat_id:[[:space:]]*-?[1-9][0-9]*[[:space:]]*$' \
    "${runtime_config}" \
    || fail "rendered chat_id is not a signed non-zero integer"
  LC_ALL=C grep -Fq \
    "bot_token_file: '${token_file}'" \
    "${runtime_config}" \
    || fail "rendered bot_token_file is invalid"
  if LC_ALL=C grep -Eq '^[[:space:]]*bot_token:' "${runtime_config}"; then
    fail "rendered configuration must not contain bot_token"
  fi

  test "$(stat -c '%a' "${runtime_config}")" = "600" \
    || fail "runtime configuration mode must be 0600"
  test "$(stat -c '%a' "${token_file}")" = "600" \
    || fail "bot token file mode must be 0600"
}

check_config() {
  render_config \
    "${TEMPLATE_PATH}" \
    "${RUNTIME_DIR}" \
    "${RUNTIME_CONFIG}" \
    "${TOKEN_FILE}"
  test -x "${AMTOOL_BIN}" || fail "amtool is unavailable"
  "${AMTOOL_BIN}" check-config "${RUNTIME_CONFIG}"
}

run_alertmanager() {
  render_config \
    "${TEMPLATE_PATH}" \
    "${RUNTIME_DIR}" \
    "${RUNTIME_CONFIG}" \
    "${TOKEN_FILE}"
  test -x "${AMTOOL_BIN}" || fail "amtool is unavailable"
  "${AMTOOL_BIN}" check-config "${RUNTIME_CONFIG}"
  test -x "${ALERTMANAGER_BIN}" || fail "Alertmanager is unavailable"
  exec "${ALERTMANAGER_BIN}" \
    "--config.file=${RUNTIME_CONFIG}" \
    "$@"
}

expect_render_failure() {
  case_name="$1"
  template_path="$2"
  case_dir="$3"
  if (
    case "${case_name}" in
      token-absent)
        unset TELEGRAM_BOT_TOKEN
        TELEGRAM_CHAT_ID='-1001234567890'
        ;;
      token-empty)
        TELEGRAM_BOT_TOKEN=''
        TELEGRAM_CHAT_ID='-1001234567890'
        ;;
      chat-id-absent)
        TELEGRAM_BOT_TOKEN='synthetic-nonsecret-value'
        unset TELEGRAM_CHAT_ID
        ;;
      chat-id-text)
        TELEGRAM_BOT_TOKEN='synthetic-nonsecret-value'
        TELEGRAM_CHAT_ID='not-an-integer'
        ;;
      chat-id-zero)
        TELEGRAM_BOT_TOKEN='synthetic-nonsecret-value'
        TELEGRAM_CHAT_ID='0'
        ;;
      residual-placeholder)
        TELEGRAM_BOT_TOKEN='synthetic-nonsecret-value'
        TELEGRAM_CHAT_ID='-1001234567890'
        ;;
      *)
        fail "unknown negative self-test"
        ;;
    esac
    export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
    render_config \
      "${template_path}" \
      "${case_dir}" \
      "${case_dir}/alertmanager.yml" \
      "${case_dir}/telegram_bot_token"
  ) >/dev/null 2>&1; then
    fail "negative self-test unexpectedly passed: ${case_name}"
  fi
  printf 'self-test %s: PASS\n' "${case_name}"
}

self_test() {
  self_test_template="$1"
  test -f "${self_test_template}" && test ! -L "${self_test_template}" \
    || fail "self-test template is missing or unsafe"
  test_root="$(mktemp -d "${TMPDIR:-/tmp}/alertmanager-render-test.XXXXXX")"
  trap 'rm -rf -- "${test_root}"' EXIT HUP INT TERM

  positive_dir="${test_root}/positive"
  positive_config="${positive_dir}/alertmanager.yml"
  positive_token="${positive_dir}/telegram_bot_token"
  TELEGRAM_BOT_TOKEN='synthetic-nonsecret-value'
  TELEGRAM_CHAT_ID='-1001234567890'
  export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
  render_config \
    "${self_test_template}" \
    "${positive_dir}" \
    "${positive_config}" \
    "${positive_token}"
  test -s "${positive_token}" || fail "positive self-test token file is empty"
  printf 'self-test positive: PASS\n'

  expect_render_failure \
    "token-absent" "${self_test_template}" "${test_root}/token-absent"
  expect_render_failure \
    "token-empty" "${self_test_template}" "${test_root}/token-empty"
  expect_render_failure \
    "chat-id-absent" "${self_test_template}" "${test_root}/chat-absent"
  expect_render_failure \
    "chat-id-text" "${self_test_template}" "${test_root}/chat-text"
  expect_render_failure \
    "chat-id-zero" "${self_test_template}" "${test_root}/chat-zero"

  residual_template="${test_root}/residual-template.yml"
  cp -- "${self_test_template}" "${residual_template}"
  printf '\nresidual: ${UNRESOLVED_PLACEHOLDER}\n' >> "${residual_template}"
  expect_render_failure \
    "residual-placeholder" "${residual_template}" "${test_root}/residual"

  rm -rf -- "${test_root}"
  trap - EXIT HUP INT TERM
  test ! -e "${test_root}" || fail "self-test temporary data was not removed"
  printf 'self-test cleanup: PASS\n'
}

case "${1:-}" in
  --check)
    check_config
    ;;
  --self-test)
    test "$#" -le 2 || fail "invalid self-test arguments"
    self_test "${2:-${TEMPLATE_PATH}}"
    ;;
  *)
    run_alertmanager "$@"
    ;;
esac
