"""Client identity for throttling, restricted to the configured proxy peers.

Uvicorn proxy-header processing is disabled in the canonical API image so that
request.client remains the actual TCP peer. Caddy replaces X-Forwarded-For with
one address; direct API callers and other containers cannot select their bucket.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket

from starlette.requests import Request

from api.config import settings


async def rate_limit_client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    hosts = [host.strip() for host in settings.TRUSTED_PROXY_HOSTS_RAW.split(",") if host.strip()]
    forwarded = request.headers.getlist("x-forwarded-for")
    if not hosts or len(forwarded) != 1 or "%" in forwarded[0]:
        return peer
    try:
        address = ipaddress.ip_address(forwarded[0].strip())
        if address.is_unspecified or address.is_multicast:
            return peer
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    for host in hosts:
        # Resolve per request: Docker may recreate Caddy at a different address.
        # Bound DNS waits and ignore headers on resolution failure.
        try:
            resolved = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(
                    host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM,
                ),
                timeout=0.5,
            )
            if any(peer_address == ipaddress.ip_address(row[4][0]) for row in resolved):
                return str(address)
        except (OSError, ValueError, TimeoutError):
            continue
    return peer
