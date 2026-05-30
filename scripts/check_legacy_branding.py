from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys


FORBIDDEN_PATTERN = re.compile(r"TKVerse|TK\s+VERSE|TkVerse|tkverse", re.IGNORECASE)
TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".txt",
    ".env",
    ".example",
    ".bak",
    ".sql",
    ".sh",
    ".ps1",
}
SKIP_PARTS = {"node_modules", ".next", ".venv", "__pycache__", "coverage", "dist", "build", "logs"}


def _is_text_candidate(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return False
    if path == Path("scripts/check_legacy_branding.py"):
        return False
    suffixes = path.suffixes
    if not suffixes:
        return False
    return any(suffix in TEXT_EXTENSIONS for suffix in suffixes)


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    matches: list[str] = []
    for raw_path in result.stdout.splitlines():
        path = Path(raw_path)
        if not _is_text_candidate(path):
            continue
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(content.splitlines(), start=1):
            if FORBIDDEN_PATTERN.search(line):
                matches.append(f"{path}:{line_number}:{line.strip()}")

    if matches:
        raise SystemExit("Legacy branding found:\n" + "\n".join(matches))

    return 0


if __name__ == "__main__":
    sys.exit(main())
