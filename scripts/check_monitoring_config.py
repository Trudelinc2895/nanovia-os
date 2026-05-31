from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS_PATH = ROOT / "infra" / "monitoring" / "prometheus.yml"
ALERTS_PATH = ROOT / "infra" / "monitoring" / "alerts.yml"
JOB_NAME_PATTERN = re.compile(r"job_name:\s*([A-Za-z0-9_-]+)")
ALERT_JOB_PATTERN = re.compile(r'job="([A-Za-z0-9_-]+)"')


def _extract_jobs(path: Path) -> set[str]:
    return set(JOB_NAME_PATTERN.findall(path.read_text(encoding="utf-8")))


def _extract_alert_jobs(path: Path) -> set[str]:
    return set(ALERT_JOB_PATTERN.findall(path.read_text(encoding="utf-8")))


def validate_monitoring_config(
    prometheus_path: Path = PROMETHEUS_PATH,
    alerts_path: Path = ALERTS_PATH,
) -> list[str]:
    prometheus_jobs = _extract_jobs(prometheus_path)
    alert_jobs = _extract_alert_jobs(alerts_path)
    errors: list[str] = []

    if "nanovia-api" not in prometheus_jobs:
        errors.append("prometheus.yml must define the nanovia-api scrape job")
    if "nanovia-api" not in alert_jobs:
        errors.append("alerts.yml must reference the nanovia-api job")

    unknown_jobs = sorted(job for job in alert_jobs if job not in prometheus_jobs)
    if unknown_jobs:
        errors.append(f"alerts.yml references unknown scrape jobs: {', '.join(unknown_jobs)}")
    return errors


def main() -> int:
    errors = validate_monitoring_config()
    if errors:
        print("Monitoring config validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Monitoring config validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
