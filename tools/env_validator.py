from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_runtime_env import (
    _looks_placeholder,
    load_env_file,
    redact_text,
    resolve_target_env,
    validate_runtime_env,
)

ENV_FILES = [
    ".env",
    ".env.example",
    "infra/env/.env.example",
    "infra/env/.env.dev.example",
    "infra/env/.env.staging.example",
]


def _is_template_file(path: str) -> bool:
    return path.endswith(".example")


def _validate_template_safety(values: dict[str, str], *, target_env: str) -> list[str]:
    errors: list[str] = []
    public_ip = values.get("PUBLIC_IP", "").strip()
    if public_ip and not _looks_placeholder(public_ip):
        errors.append("PUBLIC_IP must stay placeholder-only in committed templates")

    if target_env == "production":
        for key in ("API_BASE_URL", "PUBLIC_WEB_URL", "PRIVATE_ADMIN_URL", "ALLOWED_ORIGINS_RAW"):
            value = values.get(key, "").strip()
            if value and ("localhost" in value or "127.0.0.1" in value):
                errors.append(f"{key} contains local reference (forbidden in production template)")

    return errors


def run() -> int:
    total_errors = 0
    print("\nNanovia ENV validation\n" + "-" * 40)

    for rel in ENV_FILES:
        path = ROOT / rel
        if not path.exists():
            print(f"[MISSING] {rel}")
            continue

        values = load_env_file(path)
        target_env = resolve_target_env(rel, values)
        template_mode = _is_template_file(rel)
        errors = validate_runtime_env(values, target_env=target_env, allow_placeholders=template_mode)
        if template_mode:
            errors.extend(_validate_template_safety(values, target_env=target_env))
        gate_errors = template_mode

        print(f"\n[FILE] {rel}")
        print(f"  target_env: {target_env}")
        print(f"  keys: {len(values)}")
        print(f"  errors: {len(errors)}")
        if not gate_errors:
            print("  mode: advisory-only (local env file)")
        for error in errors[:10]:
            print(f"  - {redact_text(error)}")

        if gate_errors:
            total_errors += len(errors)

    print("\n" + "-" * 40)
    print(f"TOTAL ERRORS: {total_errors}")
    if total_errors:
        print("ENV VALIDATION FAILED")
        return 1

    print("ENV VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
