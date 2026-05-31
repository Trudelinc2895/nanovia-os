from __future__ import annotations

import argparse
import socket
import sys


def _check_tcp(host: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "open"
    except TimeoutError:
        return False, "timeout"
    except OSError as exc:
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether the Nanovia VPS target is reachable on required ports.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--ports", nargs="+", type=int, default=[22, 443])
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    failed_ports: list[int] = []
    for port in args.ports:
        ok, detail = _check_tcp(args.host, port, args.timeout)
        state = "OK" if ok else "FAIL"
        print(f"{args.host}:{port} {state} ({detail})")
        if not ok:
            failed_ports.append(port)

    if failed_ports:
        print(
            "Reachability check failed. Fix DNS, firewall, Cloudflare/origin rules, or the VPS service state before deploy.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
