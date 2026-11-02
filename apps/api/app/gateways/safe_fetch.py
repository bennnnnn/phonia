"""Shared SSRF-safe HTTP fetch helpers.

Resolves a URL's hostname once, rejects private/loopback/link-local/reserved
targets, and pins the connection to the validated IP via a rewritten URL +
explicit Host/SNI headers so DNS cannot re-resolve to something different
mid-request (closes the DNS-rebinding TOCTOU window). Callers that follow
redirects must re-validate + re-pin on every hop — see fetch_safely().

Used by app.modules.link_preview (fetching arbitrary user-submitted URLs),
app.modules.images.search (reference-photo candidates) and
app.gateways.image_gateway (fetching provider-returned image URLs) so none of
them duplicates the DNS-pinning/redirect logic.

Every fetch has an overall deadline. The client's ``httpx.Timeout`` bounds
each read, so a server that sends one byte just inside it, on every hop,
would otherwise hold the request (and an API worker slot) open for minutes.
"""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Mapping
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

PRIVATE_IP_ERR = "Blocked request to internal/private address"

_REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)


def is_blocked_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_unspecified
        or addr.is_multicast
        or addr.is_reserved
    ):
        return True
    # Non-global covers CGNAT (100.64/10) and other non-routable ranges that
    # ``is_private`` alone misses on some Python versions.
    try:
        if not addr.is_global:
            return True
    except Exception:
        # Fail closed: an address we cannot classify is never fetched.
        return True
    return False


def format_netloc(ip: str, port: int | None) -> str:
    host = f"[{ip}]" if ":" in ip else ip
    if port is not None:
        return f"{host}:{port}"
    return host


def host_header(hostname: str, port: int | None, scheme: str) -> str:
    if port is None or (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        return hostname
    return f"{hostname}:{port}"


def pin_url(url: str, ip: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(netloc=format_netloc(ip, parsed.port)))


async def resolve_external_host(url: str) -> tuple[str, str]:
    """Resolve URL hostname once and return (hostname, pinned public IP).

    Raises ValueError if the hostname is missing, unresolvable, or resolves to
    any private/loopback/link-local/reserved address. Callers must connect to
    the returned IP (not re-resolve) to close the DNS-rebinding TOCTOU window.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Unsupported URL scheme")
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("URL has no hostname")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if is_blocked_ip(literal):
            raise ValueError(PRIVATE_IP_ERR)
        return hostname, str(literal)

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(hostname, None)
    except OSError as exc:
        raise ValueError(f"Cannot resolve hostname: {hostname}") from exc

    public_ips: list[str] = []
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip_str = str(sockaddr[0])
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if is_blocked_ip(addr):
            raise ValueError(PRIVATE_IP_ERR)
        if ip_str not in public_ips:
            public_ips.append(ip_str)

    if not public_ips:
        raise ValueError(f"Cannot resolve hostname: {hostname}")
    return hostname, public_ips[0]


async def read_stream_capped(response: httpx.Response, max_body_bytes: int) -> bytes:
    """Read at most *max_body_bytes* from a streaming response body."""
    if max_body_bytes <= 0:
        return b""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        if not chunk:
            continue
        remaining = max_body_bytes - total
        if remaining <= 0:
            break
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


async def get_pinned(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_body_bytes: int | None = None,
) -> httpx.Response:
    """GET *url* via a DNS-pinned IP so resolution cannot change mid-request.

    When *max_body_bytes* is set, the body is streamed and truncated so a huge
    upstream cannot force the API to buffer gigabytes into memory.
    """
    parsed = urlparse(url)
    hostname, ip = await resolve_external_host(url)
    pinned = pin_url(url, ip)
    request_headers = dict(headers or {})
    request_headers["Host"] = host_header(hostname, parsed.port, parsed.scheme)
    extensions: dict[str, str] = {}
    if parsed.scheme == "https":
        extensions["sni_hostname"] = hostname
    if max_body_bytes is None:
        return await client.get(pinned, headers=request_headers, extensions=extensions or None)

    async with client.stream(
        "GET",
        pinned,
        headers=request_headers,
        extensions=extensions or None,
    ) as response:
        if response.status_code in _REDIRECT_STATUS_CODES:
            # Redirect bodies are unused — close without buffering.
            return httpx.Response(
                status_code=response.status_code,
                headers=_decoded_headers(response.headers),
                content=b"",
                request=response.request,
            )
        body = await read_stream_capped(response, max_body_bytes)
        return httpx.Response(
            status_code=response.status_code,
            headers=_decoded_headers(response.headers),
            content=body,
            request=response.request,
        )


# The body is already decoded and maybe cut short: these would make httpx decode it
# again (a gzip page raised DecodingError) or expect the original length.
_ENCODING_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})


def _decoded_headers(headers: httpx.Headers | Mapping[str, str]) -> httpx.Headers:
    """The upstream headers for a body that is already decompressed."""
    items = httpx.Headers(headers).multi_items()
    return httpx.Headers(
        [(name, value) for name, value in items if name.lower() not in _ENCODING_HEADERS]
    )


def fetch_client(timeout: float | httpx.Timeout) -> httpx.AsyncClient:
    """The client ``fetch_safely`` takes: redirects off, since it follows each hop itself."""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False)


async def fetch_safely(
    client: httpx.AsyncClient,
    url: str,
    *,
    deadline_seconds: float,
    headers: dict[str, str] | None = None,
    max_redirects: int = 5,
    max_body_bytes: int | None = None,
) -> httpx.Response:
    """GET *url* with SSRF-safe DNS pinning, re-validating on every redirect hop.

    The caller's client is a ``fetch_client()``, with follow_redirects=False —
    redirects are followed manually here so each hop's target is re-resolved
    and re-validated before connecting (closing the window a malicious/
    misbehaving upstream could otherwise use to redirect to an internal
    address after the initial hostname passed validation).

    *deadline_seconds* bounds the whole fetch: DNS, every redirect hop and the
    body. Past it the fetch is cancelled and ``TimeoutError`` raised.

    Pass *max_body_bytes* for untrusted bodies (link preview) so a large
    response cannot exhaust worker memory.
    """
    async with asyncio.timeout(deadline_seconds):
        current_url = url
        resp = await get_pinned(client, current_url, headers=headers, max_body_bytes=max_body_bytes)
        hops = 0
        while resp.status_code in _REDIRECT_STATUS_CODES and hops < max_redirects:
            redirect_target = resp.headers.get("Location")
            if not redirect_target:
                break
            current_url = urljoin(current_url, redirect_target)
            resp = await get_pinned(
                client, current_url, headers=headers, max_body_bytes=max_body_bytes
            )
            hops += 1
        return resp
