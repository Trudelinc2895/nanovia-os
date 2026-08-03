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


def _bash_path(path: Path) -> str:
    completed = _run_bash("pwd", cwd=path)
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _service_harness(tmp_path: Path, invocation: str, *, state: str, restart: str, ready: str):
    fake_bin = tmp_path / "service-bin"
    fake_bin.mkdir()
    restart_file = tmp_path / "restart-count"
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


def _run_postflight(tmp_path: Path, *, docker_state: str, curl_mode: str):
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
case "${FAKE_CURL_MODE}" in
  success) exit 0 ;;
  timeout) exit 28 ;;
  http_failure) exit 22 ;;
  *) exit 2 ;;
esac
""",
    )

    python_bin = Path(sys.executable).as_posix()
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
            "COMPOSE_PROJECT_NAME": "nanovia-test",
            "PUBLIC_WEB_URL": TEST_PUBLIC_WEB_URL,
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
            "FAKE_CURL_LOG": str(curl_log),
        }
    )
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
    assert " -k " not in f" {curl_calls} "


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
