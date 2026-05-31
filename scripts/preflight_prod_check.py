from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_monitoring_config import validate_monitoring_config
from check_public_endpoints import check_host
from check_secret_policy import find_secret_policy_violations
from validate_runtime_env import load_env_file, redact_text, validate_runtime_env


DEFAULT_ENV_FILE = ROOT / ".env.production"
DEFAULT_COMPOSE_FILE = ROOT / "infra" / "docker-compose.prod.yml"
DEFAULT_CADDY_FILE = ROOT / "infra" / "docker" / "Caddyfile"
DEFAULT_BACKUP_SCRIPT = ROOT / "infra" / "scripts" / "backup.sh"


def _extract_host(url: str) -> str:
    parsed = urlparse(url.strip())
    return parsed.hostname or ""


def _looks_configured(values: dict[str, str], *keys: str) -> bool:
    return any(values.get(key, "").strip() for key in keys)


def validate_static_prod_layout(
    *,
    compose_path: Path = DEFAULT_COMPOSE_FILE,
    caddy_path: Path = DEFAULT_CADDY_FILE,
    backup_path: Path = DEFAULT_BACKUP_SCRIPT,
) -> list[str]:
    errors: list[str] = []

    compose_text = compose_path.read_text(encoding="utf-8")
    caddy_text = caddy_path.read_text(encoding="utf-8")
    backup_text = backup_path.read_text(encoding="utf-8")

    if 'ports:\n      - "80:80"' not in compose_text or '      - "443:443"' not in compose_text:
        errors.append("docker-compose.prod.yml must expose Caddy on ports 80 and 443")
    if "ai_state:/var/lib/nanovia-ai" not in compose_text:
        errors.append("docker-compose.prod.yml must mount persistent AI state at /var/lib/nanovia-ai")
    if "postgres_data:/var/lib/postgresql/data" not in compose_text:
        errors.append("docker-compose.prod.yml must keep PostgreSQL on a persistent volume")
    if "redis_data:/data" not in compose_text:
        errors.append("docker-compose.prod.yml must keep Redis appendonly data on a persistent volume")
    if "import admin_ip_allow" not in caddy_text:
        errors.append("Caddyfile must enforce admin_ip_allow for private admin and metrics surfaces")
    if "handle /metrics {\n        import admin_ip_allow" not in caddy_text:
        errors.append("Caddyfile must protect /metrics behind the admin IP allowlist")
    if "{$PRIVATE_ADMIN_HOST:admin.nanovia.ca}" not in caddy_text:
        errors.append("Caddyfile must serve the private admin surface on admin.nanovia.ca")
    if "{$DOMAIN:nanovia.ca}, {$WWW_DOMAIN:www.nanovia.ca}" not in caddy_text:
        errors.append("Caddyfile must keep the public site bound to nanovia.ca and www.nanovia.ca")
    if "openssl enc -aes-256-cbc -pbkdf2" not in backup_text:
        errors.append("infra/scripts/backup.sh must encrypt backups with AES-256-CBC + PBKDF2")
    if "sha256sum" not in backup_text:
        errors.append("infra/scripts/backup.sh must emit checksums for encrypted backups")
    if "PASSPHRASE_FILE" not in backup_text or "openssl rand -base64" not in backup_text:
        errors.append("infra/scripts/backup.sh must manage a dedicated backup encryption key file")

    return errors


def collect_go_live_warnings(values: dict[str, str]) -> list[str]:
    warnings: list[str] = []

    if not _looks_configured(values, "RESEND_API_KEY", "RESEND_API_KEY_REF"):
        warnings.append("RESEND_API_KEY is absent; transactional emails stay log-only")
    if not _looks_configured(values, "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN_REF") or not values.get(
        "TELEGRAM_CHAT_ID", ""
    ).strip():
        warnings.append("Telegram alert routing is incomplete; Alertmanager notifications may be silent")
    if not _looks_configured(values, "OPENAI_API_KEY", "OPENAI_API_KEY_REF"):
        warnings.append("OPENAI_API_KEY is absent; AI features will be unavailable or degraded")

    stripe_price_keys = sorted(key for key in values if key.startswith("STRIPE_PRICE_") and values[key].strip())
    if not stripe_price_keys:
        warnings.append("No STRIPE_PRICE_* live identifiers are configured; Stripe checkout may be incomplete")

    if values.get("TURNSTILE_ENABLED", "").strip().lower() != "true":
        warnings.append("TURNSTILE_ENABLED is not true; billing and auth bot protection is reduced")

    return warnings


def validate_public_endpoints(values: dict[str, str], timeout: float) -> list[str]:
    errors: list[str] = []
    hosts = []
    for key in ("PUBLIC_WEB_URL", "PRIVATE_ADMIN_URL"):
        host = _extract_host(values.get(key, ""))
        if host:
            hosts.append(host)

    seen: set[str] = set()
    for host in hosts:
        if host in seen:
            continue
        seen.add(host)
        ok, _, detail = check_host(host, timeout)
        if not ok:
            errors.append(f"{host} DNS/TLS check failed: {detail}")
    return errors


def run_preflight(
    *,
    env_file: Path,
    allow_placeholders: bool,
    check_public_endpoints_flag: bool,
    timeout: float,
) -> tuple[list[str], list[str]]:
    values = load_env_file(env_file)
    errors = validate_runtime_env(values, target_env="production", allow_placeholders=allow_placeholders)
    errors.extend(validate_monitoring_config())
    errors.extend(find_secret_policy_violations())
    errors.extend(validate_static_prod_layout())
    if check_public_endpoints_flag:
        errors.extend(validate_public_endpoints(values, timeout))
    warnings = collect_go_live_warnings(values)
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Nanovia production go-live checks.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Allow placeholder secrets for template-mode checks.",
    )
    parser.add_argument(
        "--check-public-endpoints",
        action="store_true",
        help="Also verify DNS/TLS for PUBLIC_WEB_URL and PRIVATE_ADMIN_URL from the env file.",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    env_file = args.env_file.resolve()
    if not env_file.is_file():
        print(f"❌ Missing env file: {env_file}", file=sys.stderr)
        return 1

    errors, warnings = run_preflight(
        env_file=env_file,
        allow_placeholders=args.allow_placeholders,
        check_public_endpoints_flag=args.check_public_endpoints,
        timeout=args.timeout,
    )

    if errors:
        print("❌ Nanovia production go-live checks failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {redact_text(error)}", file=sys.stderr)
        if warnings:
            print("Warnings:", file=sys.stderr)
            for warning in warnings:
                print(f"  - {redact_text(warning)}", file=sys.stderr)
        return 1

    print("✅ Nanovia production go-live checks passed.")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {redact_text(warning)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
