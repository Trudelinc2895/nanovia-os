"""Static and executable contracts for the canonical production postflight."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import textwrap

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
RUNBOOK = REPO_ROOT / "docs" / "J21A_CANONICAL_DEPLOYMENT.md"
POSTFLIGHT = REPO_ROOT / "infra" / "scripts" / "verify-caddy-postflight.sh"
PRODUCTION_COMPOSE = REPO_ROOT / "infra" / "docker-compose.prod.yml"
CANONICAL_PRODUCTION_COMPOSE = (
    REPO_ROOT / "infra" / "docker-compose.canonical-prod.yml"
)
STAGING_COMPOSE = REPO_ROOT / "infra" / "docker-compose.staging.yml"
PRE_MIGRATION_BACKUP = REPO_ROOT / "infra" / "scripts" / "pre-migration-backup.sh"
ALERTMANAGER_RENDERER = (
    REPO_ROOT / "infra" / "monitoring" / "render-alertmanager-config.sh"
)
ALERTMANAGER_TEMPLATE = REPO_ROOT / "infra" / "monitoring" / "alertmanager.yml"
TEST_PUBLIC_WEB_URL = "https://nanovia.invalid"


def _bash_executable() -> str:
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        shutil.which("bash"),
    ]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        probe = subprocess.run(
            [candidate, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    pytest.skip("A functional Bash executable is required for postflight tests")
    raise RuntimeError("pytest.skip() unexpectedly returned")


def _write_fake_command(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _remote_deploy_script() -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    script = workflow.split("<<'ENDSSH'\n", maxsplit=1)[1]
    script = script.rsplit("\n          ENDSSH", maxsplit=1)[0]
    return textwrap.dedent(script)


def _shell_function(name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}\(\) \{{\n.*?^\}}$",
        _remote_deploy_script(),
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Unable to extract shell function {name}"
    return match.group(0)


def _pre_migration_function(name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}\(\) \{{\n.*?^\}}$",
        PRE_MIGRATION_BACKUP.read_text(encoding="utf-8"),
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Unable to extract pre-migration function {name}"
    return match.group(0)


def _run_bash(script: str, *, env: dict[str, str] | None = None, cwd=REPO_ROOT):
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    return subprocess.run(
        [_bash_executable(), "-c", script],
        cwd=cwd,
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )


def _render_compose(tmp_path: Path, *compose_files: Path, domain: str | None):
    docker = shutil.which("docker")
    assert docker is not None, "Docker Compose is required for contract tests"
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("APP_ENV=staging\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("DOMAIN", None)
    env.update(
        {
            "APP_RUNTIME_ENV_FILE": str(runtime_env),
            "COMPOSE_PROJECT_NAME": "nanovia-contract-test",
            "POSTGRES_VOLUME_NAME": "nanovia-contract-postgres",
            "REDIS_VOLUME_NAME": "nanovia-contract-redis",
            "POSTGRES_DB": "nanovia",
            "POSTGRES_USER": "nanovia",
            "POSTGRES_PASSWORD": "not-a-secret",
            "REDIS_PASSWORD": "not-a-secret",
            "NEXT_PUBLIC_API_URL": "",
            "TELEGRAM_BOT_TOKEN": "not-a-secret",
            "TELEGRAM_CHAT_ID": "1",
            "GRAFANA_ADMIN_PASSWORD": "not-a-secret",
        }
    )
    if domain is not None:
        env["DOMAIN"] = domain
    command = [docker, "compose", "-p", "nanovia-contract-test"]
    for compose_file in compose_files:
        command.extend(("-f", str(compose_file)))
    command.extend(("config", "--quiet"))
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _bash_path(path: Path) -> str:
    completed = _run_bash("pwd", cwd=path)
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _service_harness(tmp_path: Path, invocation: str, *, state: str, restart: str, ready: str):
    fake_bin = tmp_path / "service-bin"
    fake_bin.mkdir()
    _write_fake_command(
        fake_bin / "docker",
        """
if [ "${1:-}" = "ps" ]; then
  printf 'service-test-id\\n'
  exit 0
fi
if [ "${1:-}" = "inspect" ]; then
  case "${3:-}" in
    *RestartCount*)
      if [ "${FAKE_RESTART_MODE}" = "growing" ] && [ -f "${FAKE_RESTART_FILE}" ]; then
        printf '1\\n'
      else
        printf '0\\n'
        : > "${FAKE_RESTART_FILE}"
      fi
      ;;
    *State.Status*) printf '%s\\n' "${FAKE_SERVICE_STATE}" ;;
    *) exit 2 ;;
  esac
  exit 0
fi
exit 2
""",
    )
    functions = "\n\n".join(
        _shell_function(name)
        for name in (
            "single_container_for_service_any_state",
            "wait_for_stable_running",
            "wait_for_stable_http_readiness",
        )
    )
    script = f"""
set -Eeuo pipefail
export PATH="${{FAKE_BIN}}:${{PATH}}"
fail() {{ printf 'ERROR: %s\\n' "$*" >&2; exit 1; }}
compose() {{ [ "${{FAKE_READINESS_MODE}}" = success ]; }}
{functions}
{invocation}
"""
    env = {
        "FAKE_BIN": _bash_path(fake_bin),
        "COMPOSE_PROJECT_NAME": "nanovia-test",
        "FAKE_SERVICE_STATE": state,
        "FAKE_RESTART_MODE": restart,
        "FAKE_RESTART_FILE": _bash_path(tmp_path) + "/restart-count",
        "FAKE_READINESS_MODE": ready,
    }
    return _run_bash(script, env=env)


def _backup_harness(
    tmp_path: Path,
    requested_root: str,
    *,
    df_mode: str = "success",
    required_bytes: int = 1,
):
    fake_bin = tmp_path / "backup-bin"
    fake_bin.mkdir(exist_ok=True)
    df_log = tmp_path / "df.log"
    _write_fake_command(
        fake_bin / "df",
        """
printf '%s\\n' "${@: -1}" > "${FAKE_DF_LOG}"
case "${FAKE_DF_MODE}" in
  failure) exit 1 ;;
  non_numeric)
    printf 'Filesystem 1024-blocks Used Available Capacity Mounted-on\\n'
    printf 'fake 100 0 invalid 0%% /\\n'
    ;;
  *)
    printf 'Filesystem 1024-blocks Used Available Capacity Mounted-on\\n'
    printf 'fake 100 0 4096 0%% /\\n'
    ;;
esac
""",
    )
    functions = "\n\n".join(
        _shell_function(name)
        for name in ("backup_filesystem_target", "available_backup_bytes")
    )
    script = f"""
set -Eeuo pipefail
export PATH="${{FAKE_BIN}}:${{PATH}}"
fail() {{ printf 'ERROR: %s\\n' "$*" >&2; exit 1; }}
{functions}
AVAILABLE_BYTES="$(available_backup_bytes "$1")"
[ "${{AVAILABLE_BYTES}}" -ge "$2" ] || fail "Insufficient free space"
printf 'AVAILABLE_BYTES=%s\\n' "${{AVAILABLE_BYTES}}"
"""
    env = {
        "FAKE_BIN": _bash_path(fake_bin),
        "FAKE_DF_LOG": _bash_path(tmp_path) + "/df.log",
        "FAKE_DF_MODE": df_mode,
    }
    completed = subprocess.run(
        [_bash_executable(), "-c", script, "backup-test", requested_root, str(required_bytes)],
        cwd=tmp_path,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, df_log


def _run_postflight(
    tmp_path: Path,
    *,
    docker_state: str,
    curl_mode: str,
    public_web_url: str | None = TEST_PUBLIC_WEB_URL,
    domain: str | None = "nanovia.invalid",
    effective_url: str = "",
    runtime_env_file: Path | None = None,
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl_log = tmp_path / "curl.log"
    _write_fake_command(
        fake_bin / "docker",
        """
if [ "${1:-}" = "ps" ]; then
  printf 'caddy-test-id\\n'
  exit 0
fi
if [ "${1:-}" = "inspect" ]; then
  case "${FAKE_DOCKER_STATE}" in
    healthy) printf 'running|true|healthy\\n' ;;
    starting) printf 'running|true|starting\\n' ;;
    unhealthy) printf 'running|true|unhealthy\\n' ;;
    stopped) printf 'exited|false|none\\n' ;;
    *) exit 2 ;;
  esac
  exit 0
fi
exit 2
""",
    )
    _write_fake_command(
        fake_bin / "curl",
        """
printf '%s\\n' "$*" >> "${FAKE_CURL_LOG}"
target="${@: -1}"
case "${FAKE_CURL_MODE}" in
  success)
    printf '%s' "${FAKE_CURL_EFFECTIVE_URL:-${target}}"
    exit 0
    ;;
  timeout) exit 28 ;;
  http_failure) exit 22 ;;
  *) exit 2 ;;
esac
""",
    )

    python_bin = Path(sys.executable).as_posix()
    env = os.environ.copy()
    env.pop("PUBLIC_WEB_URL", None)
    env.pop("DOMAIN", None)
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
            "COMPOSE_PROJECT_NAME": "nanovia-test",
            "PYTHON_BIN": python_bin,
            "DOCKER_BIN": (fake_bin / "docker").as_posix(),
            "CURL_BIN": (fake_bin / "curl").as_posix(),
            "CADDY_POSTFLIGHT_ATTEMPTS": "2",
            "CADDY_POSTFLIGHT_DELAY_SECONDS": "0",
            "PUBLIC_POSTFLIGHT_ATTEMPTS": "2",
            "PUBLIC_POSTFLIGHT_DELAY_SECONDS": "0",
            "PUBLIC_CONNECT_TIMEOUT_SECONDS": "1",
            "PUBLIC_MAX_TIME_SECONDS": "1",
            "FAKE_DOCKER_STATE": docker_state,
            "FAKE_CURL_MODE": curl_mode,
            "FAKE_CURL_EFFECTIVE_URL": effective_url,
            "FAKE_CURL_LOG": str(curl_log),
        }
    )
    if public_web_url is not None:
        env["PUBLIC_WEB_URL"] = public_web_url
    if domain is not None:
        env["DOMAIN"] = domain
    if runtime_env_file is not None:
        env["RUNTIME_ENV_FILE"] = str(runtime_env_file)
    completed = subprocess.run(
        [_bash_executable(), POSTFLIGHT.as_posix()],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, curl_log


def test_vps_documentation_matches_workflow_variable_contract():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    for name in ("VPS_HOST", "VPS_USER", "VPS_PORT"):
        assert f"{name}: ${{{{ vars.{name} }}}}" in workflow
        assert f"| `{name}` |" in runbook
    assert "ssh-private-key: ${{ secrets.VPS_SSH_PRIVATE_KEY }}" in workflow
    assert (
        "`VPS_HOST`, `VPS_USER`, and `VPS_PORT` are variables, not secrets" in runbook
    )


def test_caddy_postflight_order_is_after_recreate_and_before_success():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    recreate = workflow.index("api ai-orchestrator web admin caddy alertmanager")
    postflight = workflow.index("bash infra/scripts/verify-caddy-postflight.sh")
    success = workflow.index("CANONICAL_DEPLOYMENT=verified")

    assert recreate < postflight < success


def test_application_postflight_order_covers_admin_and_orchestrator():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    recreate = workflow.index("api ai-orchestrator web admin caddy alertmanager")
    admin = workflow.index("wait_for_healthy admin")
    orchestrator = workflow.index("wait_for_stable_http_readiness \\\n            ai-orchestrator")
    caddy = workflow.index("bash infra/scripts/verify-caddy-postflight.sh")
    success = workflow.index("CANONICAL_DEPLOYMENT=verified")

    assert recreate < admin < orchestrator < caddy < success


def test_alertmanager_contract_is_checked_before_writers_stop_and_migration():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    alertmanager_check = workflow.index(
        "compose run --rm --no-deps -T alertmanager --check"
    )
    stop_writers = workflow.index("compose stop api ai-orchestrator")
    migration = workflow.index(
        'compose run --rm --no-deps -T api alembic upgrade "${EXPECTED_ALEMBIC_HEAD}"'
    )

    assert alertmanager_check < stop_writers < migration


def test_validated_runtime_env_is_bound_to_both_application_services():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    compose_file = (REPO_ROOT / "infra" / "docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )
    canonical_env = workflow.index('ENV_FILE="$(realpath -- "${ENV_FILE}")"')
    validation = workflow.index(
        'python3 "${RUNTIME_ENV_VALIDATOR}" \\\n'
        '            --env-file "${ENV_FILE}"'
    )
    binding = workflow.index(
        'APP_RUNTIME_ENV_FILE="${ENV_FILE}"',
        canonical_env,
    )
    compose_config = workflow.index("compose config --quiet")
    stop_writers = workflow.index("compose stop api ai-orchestrator")
    migration = workflow.index(
        'compose run --rm --no-deps -T api alembic upgrade "${EXPECTED_ALEMBIC_HEAD}"'
    )

    assert (
        canonical_env
        < validation
        < binding
        < compose_config
        < stop_writers
        < migration
    )
    assert compose_file.count("env_file: ${APP_RUNTIME_ENV_FILE:-../.env}") == 2


def test_canonical_domain_validation_precedes_every_production_mutation():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'timeout 2400 bash -seuo pipefail" <<\'ENDSSH\'' in workflow
    validation = workflow.index(
        'python3 "${RUNTIME_ENV_VALIDATOR}" \\\n'
        '            --env-file "${ENV_FILE}"'
    )
    compose_config = workflow.index("compose config --quiet")
    stop_writers = workflow.index("compose stop api ai-orchestrator")
    backup = workflow.index("bash infra/scripts/pre-migration-backup.sh")
    abandon_rollback = workflow.index("MIGRATION_STARTED=1")
    migration = workflow.index(
        'compose run --rm --no-deps -T api alembic upgrade "${EXPECTED_ALEMBIC_HEAD}"'
    )
    recreate = workflow.index("api ai-orchestrator web admin caddy alertmanager")

    assert validation < compose_config < stop_writers
    assert validation < stop_writers < backup < abandon_rollback < migration < recreate


def test_canonical_production_compose_rejects_missing_domain(tmp_path):
    completed = _render_compose(
        tmp_path,
        PRODUCTION_COMPOSE,
        CANONICAL_PRODUCTION_COMPOSE,
        domain=None,
    )

    assert completed.returncode != 0
    assert "DOMAIN is required for canonical production" in completed.stderr


def test_canonical_production_compose_accepts_domain(tmp_path):
    completed = _render_compose(
        tmp_path,
        PRODUCTION_COMPOSE,
        CANONICAL_PRODUCTION_COMPOSE,
        domain="nanovia.ca",
    )

    assert completed.returncode == 0, completed.stderr


def test_staging_compose_preserves_missing_domain_without_localhost_fallback(tmp_path):
    completed = _render_compose(
        tmp_path,
        PRODUCTION_COMPOSE,
        STAGING_COMPOSE,
        domain=None,
    )
    production_compose = PRODUCTION_COMPOSE.read_text(encoding="utf-8")

    assert completed.returncode == 0, completed.stderr
    assert "${DOMAIN:-localhost}" not in production_compose
    assert "DOMAIN: ${DOMAIN:-}" in production_compose


def test_pre_migration_backup_binds_the_selected_runtime_env_to_compose():
    script = PRE_MIGRATION_BACKUP.read_text(encoding="utf-8")
    compose_function = script.split("compose() {\n", maxsplit=1)[1].split(
        "\n}", maxsplit=1
    )[0]

    binding = compose_function.index('APP_RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE}"')
    compose = compose_function.index("docker compose")
    env_file = compose_function.index('--env-file "${RUNTIME_ENV_FILE}"')

    assert binding < compose < env_file
    assert compose_function.count("${RUNTIME_ENV_FILE}") == 2


def test_pre_migration_backup_validates_location_before_creating_it():
    script = PRE_MIGRATION_BACKUP.read_text(encoding="utf-8")
    validation = script.index(
        'REAL_BACKUP_ROOT="$(resolve_backup_root "${BACKUP_ROOT}" "${REAL_DEPLOY_PATH}")"'
    )
    creation = script.index('install -d -m 700 -- "${REAL_BACKUP_ROOT}"')

    assert validation < creation
    assert 'install -d -m 700 "${BACKUP_ROOT}"' not in script
    assert 'realpath -m -- "${requested_root}"' in script
    assert 'realpath -m -s -- "${requested_root}"' in script
    assert 'BACKUP_ROOT must not traverse symbolic links' in script


@pytest.mark.parametrize("relative_target", ["new-backups", "nested/../new-backups"])
def test_pre_migration_backup_rejects_checkout_destination_without_creation(
    tmp_path,
    relative_target,
):
    deploy_path = tmp_path / "deploy"
    deploy_path.mkdir()
    requested_root = f"{_bash_path(deploy_path)}/{relative_target}"
    functions = "\n\n".join(
        _pre_migration_function(name) for name in ("fail", "resolve_backup_root")
    )
    completed = subprocess.run(
        [
            _bash_executable(),
            "-c",
            (
                'export PATH="/usr/bin:${PATH}"\n'
                f"set -Eeuo pipefail\n{functions}\n"
                'resolve_backup_root "$1" "$2"'
            ),
            "backup-location-test",
            requested_root,
            _bash_path(deploy_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "outside the Git checkout" in completed.stderr
    assert not (deploy_path / "new-backups").exists()


def test_pre_migration_backup_rejects_symlinked_destination_without_creation(tmp_path):
    functions = "\n\n".join(
        _pre_migration_function(name) for name in ("fail", "resolve_backup_root")
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_command(
        fake_bin / "realpath",
        """
case "${1:-}" in
  -m)
    if [ "${2:-}" = "-s" ]; then
      printf '/srv/backups-link/new-backups\n'
    else
      printf '/srv/backups/new-backups\n'
    fi
    ;;
  *) exit 2 ;;
esac
""",
    )
    completed = subprocess.run(
        [
            _bash_executable(),
            "-c",
            (
                'export PATH="$3:/usr/bin:${PATH}"\n'
                f"set -Eeuo pipefail\n{functions}\n"
                'resolve_backup_root "$1" "$2"'
            ),
            "backup-symlink-test",
            "/srv/backups-link/new-backups",
            "/opt/nanovia",
            _bash_path(fake_bin),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "symbolic links" in completed.stderr


def test_pre_migration_failure_restores_checkout_before_restarting_old_writers():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    previous_commit = workflow.index('PREVIOUS_COMMIT="$(git rev-parse HEAD)"')
    recovery = workflow.index("restore_pre_migration_state()")
    recovery_checkout = workflow.index(
        'git switch --detach "${PREVIOUS_COMMIT}"',
        recovery,
    )
    recovery_verification = workflow.index(
        '[ "$(git rev-parse HEAD)" = "${PREVIOUS_COMMIT}" ]',
        recovery_checkout,
    )
    restart_writers = workflow.index(
        "start api ai-orchestrator",
        recovery_verification,
    )
    recovery_trap = workflow.index("trap restore_pre_migration_state EXIT")
    target_checkout = workflow.index('git switch --detach "${DEPLOY_SHA}"')
    stop_writers = workflow.index("compose stop api ai-orchestrator")

    assert previous_commit < recovery < recovery_trap < target_checkout < stop_writers
    assert recovery_checkout < recovery_verification < restart_writers
    assert "|| true" not in workflow[recovery:recovery_trap]


def test_pre_migration_failure_recovery_rebuilds_compose_files_from_restored_checkout():
    """The canonical overlay this change introduces may not exist in the
    previous commit's tree; the recovery restart must not hard-depend on it."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    recovery = workflow.index("restore_pre_migration_state()")
    recovery_checkout = workflow.index(
        'git switch --detach "${PREVIOUS_COMMIT}"',
        recovery,
    )
    conditional_overlay = workflow.index(
        'if [ -f "${REAL_COMPOSE_WORKING_DIR}/docker-compose.canonical-prod.yml" ]; then',
        recovery_checkout,
    )
    recovery_trap = workflow.index("trap restore_pre_migration_state EXIT")
    assert recovery_checkout < conditional_overlay < recovery_trap
    assert "RECOVERY_COMPOSE_FILES=(-f docker-compose.prod.yml)" in workflow[recovery:recovery_trap]


def test_old_writer_recovery_is_disabled_before_alembic_begins():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    recovery_trap = workflow.index("trap restore_pre_migration_state EXIT")
    stop_writers = workflow.index("compose stop api ai-orchestrator")
    backup_gate = workflow.index('|| fail "Verified backup gate is absent"')
    disable_recovery = workflow.index(
        "MIGRATION_STARTED=1\n          WRITERS_STOPPED=0\n          trap - EXIT",
        backup_gate,
    )
    migration = workflow.index(
        'compose run --rm --no-deps -T api alembic upgrade "${EXPECTED_ALEMBIC_HEAD}"'
    )
    recreate = workflow.index("compose up -d --force-recreate --no-deps")

    assert recovery_trap < stop_writers < backup_gate < disable_recovery
    assert disable_recovery < migration < recreate
    assert workflow.count("trap - EXIT") == 2


def test_compose_commands_are_bound_to_the_selected_checkout():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    canonical_compose = workflow.index(
        'REAL_COMPOSE_WORKING_DIR="$(realpath "${COMPOSE_WORKING_DIR}")"'
    )
    checkout_binding = workflow.index(
        '[ "${REAL_COMPOSE_WORKING_DIR}" = "${REAL_DEPLOY_PATH}/infra" ]'
    )
    select_commit = workflow.index('git switch --detach "${DEPLOY_SHA}"')
    compose_function = workflow.index("compose() {")
    compose_cd = workflow.index('cd "${REAL_COMPOSE_WORKING_DIR}"', compose_function)

    assert canonical_compose < checkout_binding < select_commit < compose_function < compose_cd


def test_alertmanager_renderer_self_test_covers_required_inputs():
    completed = subprocess.run(
        [
            _bash_executable(),
            ALERTMANAGER_RENDERER.as_posix(),
            "--self-test",
            ALERTMANAGER_TEMPLATE.as_posix(),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    for case_name in (
        "positive",
        "token-absent",
        "token-empty",
        "chat-id-absent",
        "chat-id-text",
        "chat-id-zero",
        "residual-placeholder",
        "cleanup",
    ):
        assert f"self-test {case_name}: PASS" in completed.stdout
    assert "synthetic-nonsecret-value" not in completed.stdout
    assert "synthetic-nonsecret-value" not in completed.stderr


def test_orchestrator_stable_readiness_succeeds(tmp_path):
    completed = _service_harness(
        tmp_path,
        "wait_for_stable_http_readiness ai-orchestrator http://127.0.0.1:8020/health 2 0",
        state="running",
        restart="fixed",
        ready="success",
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("state", ["exited", "restarting"])
def test_orchestrator_readiness_rejects_non_running_states(tmp_path, state):
    completed = _service_harness(
        tmp_path,
        "wait_for_stable_http_readiness ai-orchestrator http://127.0.0.1:8020/health 2 0",
        state=state,
        restart="fixed",
        ready="success",
    )

    assert completed.returncode != 0
    assert "ai-orchestrator is not running" in completed.stderr


def test_orchestrator_readiness_rejects_growing_restart_count(tmp_path):
    completed = _service_harness(
        tmp_path,
        "wait_for_stable_http_readiness ai-orchestrator http://127.0.0.1:8020/health 2 0",
        state="running",
        restart="growing",
        ready="success",
    )

    assert completed.returncode != 0
    assert "restarted during readiness checks" in completed.stderr


def test_orchestrator_readiness_times_out_fail_closed(tmp_path):
    completed = _service_harness(
        tmp_path,
        "wait_for_stable_http_readiness ai-orchestrator http://127.0.0.1:8020/health 2 0",
        state="running",
        restart="fixed",
        ready="failure",
    )

    assert completed.returncode != 0
    assert "did not become stably ready" in completed.stderr


def test_stable_running_fallback_requires_unchanged_running_container(tmp_path):
    completed = _service_harness(
        tmp_path,
        "wait_for_stable_running alertmanager 2 0",
        state="running",
        restart="fixed",
        ready="success",
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("directory_name", ["backups", "mounted-backups"])
def test_backup_df_targets_existing_backup_directory(tmp_path, directory_name):
    backup_root = tmp_path / directory_name
    backup_root.mkdir()
    requested = _bash_path(backup_root)

    completed, df_log = _backup_harness(tmp_path, requested)

    assert completed.returncode == 0, completed.stderr
    assert df_log.read_text(encoding="utf-8").strip() == requested


def test_backup_df_uses_nearest_existing_ancestor_for_nested_absent_path(tmp_path):
    existing = tmp_path / "storage"
    existing.mkdir()
    requested = f"{_bash_path(existing)}/nested/backups"

    completed, df_log = _backup_harness(tmp_path, requested)

    assert completed.returncode == 0, completed.stderr
    assert df_log.read_text(encoding="utf-8").strip() == _bash_path(existing)


def test_backup_df_normalizes_trailing_slash(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    requested = _bash_path(backup_root)

    completed, df_log = _backup_harness(tmp_path, requested + "/")

    assert completed.returncode == 0, completed.stderr
    assert df_log.read_text(encoding="utf-8").strip() == requested


def test_backup_df_accepts_filesystem_root(tmp_path):
    completed, df_log = _backup_harness(tmp_path, "/")

    assert completed.returncode == 0, completed.stderr
    assert df_log.read_text(encoding="utf-8").strip() == "/"


@pytest.mark.parametrize("requested", ["", "relative/backups"])
def test_backup_root_rejects_empty_or_relative_without_calling_df(tmp_path, requested):
    completed, df_log = _backup_harness(tmp_path, requested)

    assert completed.returncode != 0
    assert not df_log.exists()


def test_backup_root_rejects_existing_file_without_calling_df(tmp_path):
    backup_file = tmp_path / "backup-file"
    backup_file.write_text("not a directory", encoding="utf-8")

    completed, df_log = _backup_harness(tmp_path, _bash_path(tmp_path) + "/backup-file")

    assert completed.returncode != 0
    assert "not a directory" in completed.stderr
    assert not df_log.exists()


@pytest.mark.parametrize("df_mode", ["failure", "non_numeric"])
def test_backup_space_check_fails_closed_on_df_errors(tmp_path, df_mode):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()

    completed, _ = _backup_harness(
        tmp_path,
        _bash_path(backup_root),
        df_mode=df_mode,
    )

    assert completed.returncode != 0


def test_backup_space_check_rejects_insufficient_capacity(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()

    completed, _ = _backup_harness(
        tmp_path,
        _bash_path(backup_root),
        required_bytes=4_194_305,
    )

    assert completed.returncode != 0
    assert "Insufficient free space" in completed.stderr


def test_caddy_postflight_succeeds_with_healthy_service_and_https(tmp_path):
    completed, curl_log = _run_postflight(
        tmp_path,
        docker_state="healthy",
        curl_mode="success",
    )

    assert completed.returncode == 0, completed.stderr
    assert "CADDY_POSTFLIGHT=verified" in completed.stdout
    curl_calls = curl_log.read_text(encoding="utf-8")
    curl_arguments = [
        argument
        for call in curl_calls.splitlines()
        for argument in shlex.split(call)
    ]
    expected_urls = {
        f"{TEST_PUBLIC_WEB_URL}/api/v1/health/ready",
        f"{TEST_PUBLIC_WEB_URL}/",
    }
    assert expected_urls.issubset(set(curl_arguments))
    assert "--proto =https" in curl_calls
    assert "--write-out %{url_effective}" in curl_calls
    assert " -k " not in f" {curl_calls} "


def test_caddy_postflight_reads_public_host_pair_from_runtime_env(tmp_path):
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text(
        "PUBLIC_WEB_URL=https://nanovia.invalid\nDOMAIN=nanovia.invalid\n",
        encoding="utf-8",
    )

    completed, _ = _run_postflight(
        tmp_path,
        docker_state="healthy",
        curl_mode="success",
        public_web_url=None,
        domain=None,
        runtime_env_file=runtime_env,
    )

    assert completed.returncode == 0, completed.stderr
    assert "CADDY_POSTFLIGHT=verified" in completed.stdout


def test_caddy_postflight_rejects_public_url_domain_mismatch_before_probe(tmp_path):
    completed, curl_log = _run_postflight(
        tmp_path,
        docker_state="healthy",
        curl_mode="success",
        public_web_url="https://unrelated.invalid",
    )

    assert completed.returncode != 0
    assert "same canonical HTTPS host" in completed.stderr
    assert "CADDY_POSTFLIGHT=verified" not in completed.stdout
    assert not curl_log.exists()


@pytest.mark.parametrize(
    "effective_url",
    [
        pytest.param("https://unrelated.invalid/ready", id="external-host"),
        pytest.param("http://nanovia.invalid/ready", id="http-downgrade"),
        pytest.param("https://nanovia.invalid:444/ready", id="unexpected-port"),
    ],
)
def test_caddy_postflight_rejects_noncanonical_final_redirect_host(
    tmp_path,
    effective_url,
):
    completed, _ = _run_postflight(
        tmp_path,
        docker_state="healthy",
        curl_mode="success",
        effective_url=effective_url,
    )

    assert completed.returncode != 0
    assert "Public API readiness probe failed" in completed.stderr
    assert "CADDY_POSTFLIGHT=verified" not in completed.stdout


def test_caddy_postflight_accepts_same_host_redirect_and_explicit_https_port(tmp_path):
    completed, _ = _run_postflight(
        tmp_path,
        docker_state="healthy",
        curl_mode="success",
        public_web_url="https://nanovia.invalid:443",
        effective_url="https://nanovia.invalid:443/final",
    )

    assert completed.returncode == 0, completed.stderr
    assert "CADDY_POSTFLIGHT=verified" in completed.stdout


@pytest.mark.parametrize(
    ("curl_mode", "expected_error"),
    [
        ("timeout", "Public API readiness probe failed"),
        ("http_failure", "Public API readiness probe failed"),
    ],
)
def test_caddy_postflight_fails_closed_on_public_probe_errors(
    tmp_path,
    curl_mode,
    expected_error,
):
    completed, _ = _run_postflight(
        tmp_path,
        docker_state="healthy",
        curl_mode=curl_mode,
    )

    assert completed.returncode != 0
    assert expected_error in completed.stderr
    assert "CADDY_POSTFLIGHT=verified" not in completed.stdout


def test_caddy_postflight_fails_closed_on_unhealthy_service(tmp_path):
    completed, curl_log = _run_postflight(
        tmp_path,
        docker_state="unhealthy",
        curl_mode="success",
    )

    assert completed.returncode != 0
    assert "Caddy reported an unhealthy container state" in completed.stderr
    assert not curl_log.exists()
