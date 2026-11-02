"""HTTP security headers applied to every API response.

CORS handles cross-origin policy; this adds the baseline defense-in-depth
headers (content-type sniffing, framing, referrer, transport security) that
aren't worth scattering per-route. HSTS is only emitted behind TLS in
production — sending it over HTTP would pin a broken state for the browser.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

# Subclasses so Starlette's automatic server-timeout middleware doesn't trip
# on a bare dict and so the headers are trivially auditable.
_BASE_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permitted-Cross-Domain-Policies": "none",
}


class SecurityHeadersMiddleware:
    """Add baseline security headers to each HTTP response.

    Implemented as raw ASGI (not BaseHTTPMiddleware) so it doesn't add a
    per-request coroutine hop on the hot chat/streaming path.
    """

    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        self._app = app
        self._headers: list[tuple[str, str]] = list(_BASE_HEADERS.items())
        if enable_hsts:
            # 1 year, include subdomains, preload — only when we know we're
            # behind TLS (production). Set via config, not guessed here.
            self._headers.append(
                ("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Starlette encodes header names as bytes; normalize to
                # lowercase str so a route that already set a header (e.g.
                # attachment routes set their own nosniff) is detected and not
                # duplicated into "nosniff, nosniff".
                existing: set[str] = set()
                for k, _ in headers:
                    if isinstance(k, bytes | bytearray):
                        existing.add(k.decode("latin-1", "replace").lower())
                    else:
                        existing.add(str(k).lower())
                for name, value in self._headers:
                    if name.lower() in existing:
                        continue
                    headers.append((name.encode("latin-1"), value.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self._app(scope, receive, send_with_headers)
