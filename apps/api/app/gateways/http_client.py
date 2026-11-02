"""Pooled, keep-alive httpx.AsyncClient shared across outbound gateway calls.

Each external gateway used to open a fresh httpx.AsyncClient per call, paying
a new TCP+TLS handshake every time even for repeated calls to the same host
within seconds. Gateways call get_pooled_client(<NAMED>_TIMEOUT_SECONDS)
instead, which lazily creates one client per distinct timeout/retry policy and
reuses it for the life of the process; process shutdown closes them all.

A new gateway does the same: one named timeout constant (or a setting) and
this client. A download through ``safe_fetch`` opens its own
(``safe_fetch.fetch_client``): it checks every redirect hop itself.
"""

from __future__ import annotations

import httpx

_clients: dict[tuple[float, int], httpx.AsyncClient] = {}


def get_pooled_client(timeout: float, *, connect_retries: int = 0) -> httpx.AsyncClient:
    """Return a pooled client; optionally retry connection setup failures.

    httpx transport retries are intentionally limited to connection errors and
    connection timeouts. They do not replay arbitrary HTTP responses, so using
    them for the Realtime token-mint request is safe and keeps a transient TLS
    failure from immediately killing Live Talk.
    """
    key = (timeout, connect_retries)
    client = _clients.get(key)
    if client is None or client.is_closed:
        transport = httpx.AsyncHTTPTransport(retries=connect_retries)
        client = httpx.AsyncClient(timeout=timeout, transport=transport)
        _clients[key] = client
    return client


async def aclose_pooled_clients() -> None:
    """Release pooled connections on app shutdown."""
    clients = list(_clients.values())
    _clients.clear()
    for client in clients:
        await client.aclose()
