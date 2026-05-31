from __future__ import annotations

import argparse
import socket
import ssl
import sys


def _resolve(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def _tls_head(host: str, timeout: float) -> tuple[bool, str]:
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                tls_sock.sendall(
                    f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nUser-Agent: nanovia-endpoint-check\r\n\r\n".encode(
                        "ascii"
                    )
                )
                data = tls_sock.recv(128).decode("iso-8859-1", errors="replace")
        first_line = data.splitlines()[0] if data else "No HTTP response"
        return True, first_line
    except Exception as exc:
        return False, str(exc)


def _check_host(host: str, timeout: float) -> tuple[bool, list[str], str]:
    ips = _resolve(host)
    ok, detail = _tls_head(host, timeout)
    return ok, ips, detail


def check_host(host: str, timeout: float) -> tuple[bool, list[str], str]:
    return _check_host(host, timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Nanovia public DNS and HTTPS/TLS endpoints.")
    parser.add_argument("--hosts", nargs="+", default=["nanovia.ca", "admin.nanovia.ca"])
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    failures = 0
    for host in args.hosts:
        ok, ips, detail = check_host(host, args.timeout)
        state = "OK" if ok else "FAIL"
        print(f"{host} {state} ips={','.join(ips)} detail={detail}")
        if not ok:
            failures += 1

    if failures:
        print("One or more public endpoints failed DNS/TLS validation.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
