from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request


def resolve_a_record(hostname: str) -> str:
    try:
        return socket.gethostbyname(hostname)
    except OSError:
        return "UNRESOLVED"


def fetch(url: str, *, verify_tls: bool = True) -> tuple[str, str]:
    context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "nanovia-public-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=context) as resp:
            body = resp.read(1500).decode("utf-8", errors="replace")
            return str(resp.status), body
    except urllib.error.HTTPError as exc:
        body = exc.read(1500).decode("utf-8", errors="replace")
        return str(exc.code), body
    except Exception as exc:  # noqa: BLE001
        return "ERROR", str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Nanovia public entrypoints.")
    parser.add_argument("--domain", default="nanovia.ca")
    parser.add_argument("--ip", default="167.114.155.166")
    args = parser.parse_args()

    checks: list[tuple[str, str, str]] = []
    for host in (args.domain, f"www.{args.domain}", f"api.{args.domain}"):
        checks.append((f"DNS {host}", resolve_a_record(host), ""))

    status, body = fetch(f"https://{args.domain}/login")
    checks.append(("HTTPS login", status, body[:180]))

    status, body = fetch(f"https://api.{args.domain}/api/v1/health/ready")
    checks.append(("API ready", status, body[:180]))

    status, body = fetch(f"https://{args.domain}/api/v1/health/public-entrypoint")
    checks.append(("Public entrypoint diag", status, body[:180]))

    status, body = fetch(f"http://{args.ip}/login", verify_tls=False)
    checks.append(("Raw IP login", status, body[:180]))

    print("=== NANOVIA PUBLIC ENTRYPOINT CHECK ===")
    for label, status, detail in checks:
        print(f"- {label}: {status}")
        if detail:
            print(f"  {detail.strip()}")

    stale_signals = []
    if any(status == "UNRESOLVED" for label, status, _ in checks if label.startswith("DNS ")):
        stale_signals.append("DNS records are unresolved")
    if any(label == "Public entrypoint diag" and status != "200" for label, status, _ in checks):
        stale_signals.append("live API is missing the new public-entrypoint diagnostic")
    if any(label == "HTTPS login" and "KT Monetization OS" in detail for label, _, detail in checks):
        stale_signals.append("live frontend still serves old KT branding")
    if any(label == "Raw IP login" and status == "200" for label, status, _ in checks):
        stale_signals.append("raw IP still serves login directly instead of redirecting")

    print("\n=== SUMMARY ===")
    if stale_signals:
        print(json.dumps({"status": "stale-or-misconfigured", "signals": stale_signals}, indent=2))
        return 1

    print(json.dumps({"status": "looks-consistent"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
