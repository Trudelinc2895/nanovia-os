"""Execute the staging migration gate with injected Docker failure scenarios.

These test ordering and fail-closed behavior; they do not claim a real database
restore or Docker build occurred.
"""
from pathlib import Path
import os
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "infra/scripts/staging-migrate.sh"
SHA = "a" * 40


@pytest.mark.parametrize("failure", [
    "", "build", "multiple-heads", "wrong-image", "wrong-volume", "empty-dump",
    "invalid-dump", "unknown-current", "upgrade",
])
def test_staging_gate_requires_exact_image_head_and_backup_before_upgrade(tmp_path, failure):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "calls.log"
    commands = {
        "git": 'case "$1" in rev-parse) echo "$TARGET_SHA";; status) :;; esac',
        "python3": 'echo validate >> "$CALL_LOG"',
        "docker": r'''
echo "$*" >> "$CALL_LOG"
if [ "$1" = image ]; then
  if [ "$FAILURE" = wrong-image ]; then echo wrong; else echo "$TARGET_SHA"; fi
  exit 0
fi
if [ "$1" = inspect ]; then
  if [ "$FAILURE" = wrong-volume ]; then echo production_data; else echo nanovia-staging_postgres_data; fi
  exit 0
fi
while [ "$1" != .env.staging ]; do shift; done
shift
case "$1" in
  build) [ "$FAILURE" != build ];;
  images) echo sha256:test;;
  ps) echo test-db;;
  run)
    case "${@: -1}" in
      heads)
        echo 'd8f5b4c3a210 (head)'
        if [ "$FAILURE" = multiple-heads ]; then echo 'other (head)'; fi;;
      current)
        [ "$FAILURE" != unknown-current ] || exit 1
        if [ -f "$UPGRADED" ]; then echo 'd8f5b4c3a210 (head)'; else echo 'c7e4a91f2b60'; fi;;
      d8f5b4c3a210)
        [ "$FAILURE" != upgrade ] || exit 1
        touch "$UPGRADED";;
    esac;;
  exec)
    if [ "$FAILURE" = empty-dump ]; then exit 0; fi
    if [ "${@: -1}" = --list ]; then
      [ "$FAILURE" != invalid-dump ]
    else
      echo custom-dump-fixture
    fi;;
esac
''',
    }
    for name, body in commands.items():
        command = binaries / name
        command.write_text("#!/usr/bin/env bash\nset -eu\n" + body)
        command.chmod(0o755)
    env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}", TARGET_ENV="staging",
               TARGET_SHA=SHA, DEPLOY_PATH=str(checkout), FAILURE=failure,
               CALL_LOG=str(log), UPGRADED=str(tmp_path / "upgraded"))
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    calls = log.read_text()
    if failure:
        assert result.returncode != 0, result.stdout + result.stderr
        if failure != "upgrade":
            assert "alembic upgrade" not in calls
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert calls.index(" build ") < calls.index("alembic heads")
        assert calls.index("pg_dump") < calls.index("pg_restore --list") < calls.index("alembic upgrade")
        assert "alembic upgrade d8f5b4c3a210" in calls
        snapshots = list((tmp_path / ".nanovia-staging-backups").glob("*/postgres.dump"))
        assert len(snapshots) == 1
        assert snapshots[0].stat().st_mode & 0o077 == 0
