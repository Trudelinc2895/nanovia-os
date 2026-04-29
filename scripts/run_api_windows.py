from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _remap_local_host(raw_url: str, *, aliases: set[str]) -> str:
    if not raw_url:
        return raw_url
    parsed = urlsplit(raw_url)
    hostname = (parsed.hostname or "").lower()
    if hostname not in aliases:
        return raw_url

    netloc = parsed.netloc
    if "@" in netloc:
        userinfo, hostpart = netloc.rsplit("@", 1)
        hostpart = hostpart.replace(hostname, "127.0.0.1", 1)
        netloc = f"{userinfo}@{hostpart}"
    else:
        netloc = netloc.replace(hostname, "127.0.0.1", 1)
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    if os.name == "nt" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    os.environ["DATABASE_URL"] = _remap_local_host(
        os.environ.get("DATABASE_URL", ""),
        aliases={"db", "postgres"},
    )
    os.environ["REDIS_URL"] = _remap_local_host(
        os.environ.get("REDIS_URL", ""),
        aliases={"redis"},
    )

    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=8010,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
