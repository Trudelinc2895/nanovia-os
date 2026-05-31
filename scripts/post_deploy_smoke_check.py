from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from validate_runtime_env import load_env_file, redact_text


def _request(method: str, url: str, timeout: float, *, allow_redirects: bool = False) -> requests.Response:
    return requests.request(method, url, timeout=timeout, allow_redirects=allow_redirects)


def _expect_status(url: str, allowed_statuses: set[int], timeout: float, label: str) -> list[str]:
    errors: list[str] = []
    try:
        response = _request("GET", url, timeout)
    except requests.RequestException as exc:
        return [f"{label} request failed for {url}: {exc}"]
    if response.status_code not in allowed_statuses:
        errors.append(f"{label} returned unexpected status {response.status_code} for {url}")
    return errors


def run_smoke_checks(env_values: dict[str, str], timeout: float) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    public_base = env_values.get("PUBLIC_WEB_URL", "").rstrip("/")
    admin_base = env_values.get("PRIVATE_ADMIN_URL", "").rstrip("/")

    if not public_base:
        errors.append("PUBLIC_WEB_URL is required for post-deploy smoke checks")
        return errors, warnings

    errors.extend(_expect_status(public_base, {200}, timeout, "public web"))
    errors.extend(_expect_status(urljoin(f"{public_base}/", "health"), {200}, timeout, "health"))
    errors.extend(_expect_status(urljoin(f"{public_base}/", "ready"), {200}, timeout, "readiness"))

    metrics_url = urljoin(f"{public_base}/", "metrics")
    try:
        metrics_response = _request("GET", metrics_url, timeout)
        if metrics_response.status_code not in {401, 403}:
            errors.append(f"metrics endpoint should not be public, got {metrics_response.status_code} for {metrics_url}")
    except requests.RequestException as exc:
        errors.append(f"metrics request failed for {metrics_url}: {exc}")

    plans_url = urljoin(f"{public_base}/", "api/v1/billing/plans")
    try:
        plans_response = _request("GET", plans_url, timeout)
        if plans_response.status_code != 200:
            warnings.append(f"billing plans returned {plans_response.status_code} for {plans_url}")
    except requests.RequestException as exc:
        warnings.append(f"billing plans request failed for {plans_url}: {exc}")

    if admin_base:
        try:
            admin_response = _request("GET", admin_base, timeout)
            if admin_response.status_code >= 500:
                errors.append(f"private admin host returned {admin_response.status_code} for {admin_base}")
        except requests.RequestException as exc:
            errors.append(f"private admin host failed for {admin_base}: {exc}")
    else:
        warnings.append("PRIVATE_ADMIN_URL is empty; private admin smoke check skipped")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Nanovia post-deploy smoke checks against live endpoints.")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.production")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    env_file = args.env_file.resolve()
    if not env_file.is_file():
        print(f"❌ Missing env file: {env_file}", file=sys.stderr)
        return 1

    values = load_env_file(env_file)
    errors, warnings = run_smoke_checks(values, args.timeout)

    if errors:
        print("❌ Nanovia post-deploy smoke checks failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {redact_text(error)}", file=sys.stderr)
        if warnings:
            print("Warnings:", file=sys.stderr)
            for warning in warnings:
                print(f"  - {redact_text(warning)}", file=sys.stderr)
        return 1

    print("✅ Nanovia post-deploy smoke checks passed.")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {redact_text(warning)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
