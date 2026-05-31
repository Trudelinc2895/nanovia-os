from __future__ import annotations

import argparse
import base64
import os
import secrets
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / ".env.example"
DEFAULT_OUTPUT = ROOT / ".env.production"
PLACEHOLDER_TOKENS = ("CHANGE_ME", "REPLACE_ME", "REPLACE_WITH", "GENERATE_WITH")


def _parse_env(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _get_value(lines: list[str], key: str) -> str:
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):]
    return ""


def _is_placeholder(value: str) -> bool:
    stripped = value.strip()
    return not stripped or any(token in stripped for token in PLACEHOLDER_TOKENS)


def _upsert(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    replacement = f"{key}={value}"
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return lines
    lines.append(replacement)
    return lines


def _random_password(length: int = 40) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _random_hex(bytes_len: int = 32) -> str:
    return secrets.token_hex(bytes_len)


def _random_fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def _current_or_generated(lines: list[str], key: str, generator) -> str:
    current = _get_value(lines, key)
    if not _is_placeholder(current):
        return current
    return generator()


def _env_first(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _validate_env_file(path: Path) -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "validate_runtime_env.py"),
        "--env-file",
        str(path),
        "--target-env",
        "production",
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def build_env(template: Path, output: Path, domain: str, public_ip: str) -> int:
    source = output if output.exists() else template
    lines = _parse_env(source)

    admin_domain = f"admin.{domain}"
    jwt_secret = _current_or_generated(lines, "JWT_SECRET_KEY", lambda: _random_hex(32))
    postgres_password = _current_or_generated(lines, "POSTGRES_PASSWORD", _random_password)
    redis_password = _current_or_generated(lines, "REDIS_PASSWORD", _random_password)

    admin_allowlist = _env_first("ADMIN_ALLOWED_IPS", "ADMIN_ALLOWED_IPS_RAW", "ADMIN_ALLOWED_IP")

    updates = {
        "APP_ENV": "production",
        "APP_NAME": "Nanovia OS",
        "APP_RUNTIME_ENV_FILE": "../.env.production",
        "DOMAIN": domain,
        "API_BASE_URL": f"https://{domain}",
        "NEXT_PUBLIC_API_URL": f"https://{domain}",
        "PUBLIC_WEB_URL": f"https://{domain}",
        "PRIVATE_ADMIN_URL": f"https://{admin_domain}",
        "PRIVATE_ADMIN_HOST": admin_domain,
        "ALLOWED_ORIGINS_RAW": f"https://{domain},https://www.{domain},https://{admin_domain}",
        "AI_STATE_DIR": "/var/lib/nanovia-ai",
        "JWT_SECRET_KEY": jwt_secret,
        "SECRET_KEY": jwt_secret,
        "POSTGRES_PASSWORD": postgres_password,
        "DATABASE_URL": f"postgresql+psycopg://ktadmin:{postgres_password}@postgres:5432/ktmonetization",
        "REDIS_PASSWORD": redis_password,
        "REDIS_URL": f"redis://:{redis_password}@redis:6379/0",
        "GRAFANA_ADMIN_PASSWORD": _current_or_generated(lines, "GRAFANA_ADMIN_PASSWORD", _random_password),
        "TOTP_ENCRYPTION_KEY": _current_or_generated(lines, "TOTP_ENCRYPTION_KEY", _random_fernet_key),
        "AI_ADMIN_API_KEY": _current_or_generated(lines, "AI_ADMIN_API_KEY", lambda: _random_password(48)),
        "ADMIN_ALLOWED_IPS": admin_allowlist,
        "ADMIN_ALLOWED_IP": admin_allowlist,
        "STRIPE_SECRET_KEY": _env_first("STRIPE_SECRET_KEY"),
        "STRIPE_PUBLIC_KEY": _env_first("STRIPE_PUBLIC_KEY"),
        "STRIPE_WEBHOOK_SECRET": _env_first("STRIPE_WEBHOOK_SECRET"),
        "OPENAI_API_KEY": _env_first("OPENAI_API_KEY"),
        "TURNSTILE_SITE_KEY": _env_first("TURNSTILE_SITE_KEY"),
        "NEXT_PUBLIC_TURNSTILE_SITE_KEY": _env_first("NEXT_PUBLIC_TURNSTILE_SITE_KEY", "TURNSTILE_SITE_KEY"),
        "TURNSTILE_SECRET_KEY": _env_first("TURNSTILE_SECRET_KEY"),
        "TELEGRAM_BOT_TOKEN": _env_first("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_CHAT_ID": _env_first("TELEGRAM_CHAT_ID"),
    }
    if public_ip:
        updates["PUBLIC_IP"] = public_ip

    turnstile_enabled = all(
        updates[key].strip()
        for key in ("TURNSTILE_SITE_KEY", "NEXT_PUBLIC_TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY")
    )
    updates["TURNSTILE_ENABLED"] = "true" if turnstile_enabled else "false"

    for key, value in updates.items():
        if value:
            _upsert(lines, key, value)

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {output}")

    missing_live = [
        key
        for key in ("ADMIN_ALLOWED_IPS", "STRIPE_SECRET_KEY", "STRIPE_PUBLIC_KEY", "STRIPE_WEBHOOK_SECRET")
        if _is_placeholder(_get_value(lines, key))
    ]
    if missing_live:
        print("Missing live inputs:", file=sys.stderr)
        for key in missing_live:
            print(f"  - {key}", file=sys.stderr)
        print("Export those values in your shell and rerun this script.", file=sys.stderr)
        return 1

    return _validate_env_file(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a validated Nanovia .env.production file.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--domain", default=os.environ.get("DOMAIN", "nanovia.ca"))
    parser.add_argument("--public-ip", default=os.environ.get("PUBLIC_IP", ""))
    args = parser.parse_args()

    return build_env(
        template=args.template.resolve(),
        output=args.output.resolve(),
        domain=args.domain.strip(),
        public_ip=args.public_ip.strip(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
