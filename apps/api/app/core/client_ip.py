"""Resolve client IP for rate limiting — only trust forwarded headers behind a known proxy."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping

from starlette.requests import HTTPConnection

from app.core.config import Settings


def _parse_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def _is_trusted_proxy(host: str, settings: Settings) -> bool:
    parsed = _parse_ip(host)
    if parsed is None:
        return False
    addr = ipaddress.ip_address(parsed)
    for raw in settings.trusted_proxy_cidrs.split(","):
        cidr = raw.strip()
        if not cidr:
            continue
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def _client_from_x_forwarded_for(forwarded: str, settings: Settings) -> str | None:
    """Pick the rightmost hop that is not a trusted proxy.

    Clients can prepend spoofed addresses to X-Forwarded-For; proxies append.
    Walking from the right and skipping trusted proxies yields the connecting
    client as seen by the outermost trusted hop — not the leftmost spoof.
    """
    hops: list[str] = []
    for part in forwarded.split(","):
        parsed = _parse_ip(part)
        if parsed is not None:
            hops.append(parsed)
    for hop in reversed(hops):
        if not _is_trusted_proxy(hop, settings):
            return hop
    return None


def _resolve_client_ip(
    host: str | None,
    headers: Mapping[str, str],
    settings: Settings,
) -> str:
    """Shared IP resolution used by both REST and WebSocket rate limiters.

    Accepts the raw peer host + a header mapping so it works for both
    `starlette.requests.Request` and `fastapi.WebSocket` (whose `.headers`
    is case-insensitive but otherwise dict-like).
    """
    peer = host or "unknown"
    if not settings.trust_x_forwarded_for:
        return peer
    if not _is_trusted_proxy(peer, settings):
        return peer

    # Fly sets this to the edge-seen client IP; prefer it over XFF when present.
    fly_ip = _parse_ip(headers.get("fly-client-ip", ""))
    if fly_ip is not None:
        return fly_ip

    forwarded = headers.get("x-forwarded-for", "")
    from_xff = _client_from_x_forwarded_for(forwarded, settings) if forwarded.strip() else None
    return from_xff or peer


def client_ip(connection: HTTPConnection, settings: Settings) -> str:
    """The client IP of a request or a WebSocket handshake, under the same trust rules.

    A WebSocket needs the same fly-client-ip / XFF handling as REST so a handshake
    behind Fly is keyed on the real edge IP, not the proxy's.
    """
    return _resolve_client_ip(
        connection.client.host if connection.client else None,
        connection.headers,
        settings,
    )
