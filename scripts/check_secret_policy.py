from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ENV_FILES = {
    ".env.example",
    ".env.sandbox.example",
    "infra/env/.env.example",
    "infra/env/.env.staging.example",
}
SKIP_DIRS = {
    ".git",
    ".next",
    ".venv",
    "node_modules",
    "__pycache__",
    ".ruff_cache",
}
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".db",
    ".pyc",
    ".woff",
    ".woff2",
}
PATTERNS = {
    "Stripe live secret": re.compile(r"sk_live_[A-Za-z0-9]+"),
    "GitHub personal token": re.compile(r"github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+"),
    "Stripe webhook secret": re.compile(r"whsec_(?!test|replace|REPLACE|example|EXAMPLE)[A-Za-z0-9_]{12,}"),
    "OpenAI project/admin/service key": re.compile(r"sk_(?:proj|svcacct|admin)-[A-Za-z0-9\-_]+"),
    "Hardcoded OPENAI_API_KEY": re.compile(
        r"OPENAI_API_KEY\s*=\s*(?:\"|')?(?:sk_(?:proj|svcacct|admin)-[A-Za-z0-9\-_]{12,}|sk-(?!REPLACE|replace|\.{3})[A-Za-z0-9\-_]{16,})(?:\"|')?"
    ),
}


def _iter_files(root: Path = ROOT) -> list[Path]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files"],
            cwd=root,
            text=True,
        )
        return [root / line for line in output.splitlines() if line.strip()]
    except Exception:
        pass

    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        files.append(path)
    return files


def find_secret_policy_violations(root: Path = ROOT) -> list[str]:
    violations: list[str] = []
    for path in _iter_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in ALLOWED_ENV_FILES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    violations.append(f"{relative}:{index}: {label}")
    return violations


def main() -> int:
    violations = find_secret_policy_violations()
    if violations:
        print("Secret policy violations detected:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1
    print("Secret policy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
