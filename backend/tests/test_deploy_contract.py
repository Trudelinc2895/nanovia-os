"""Static and executable contracts for the canonical production postflight."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys

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
