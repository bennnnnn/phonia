"""Attach a request ID to every HTTP response for log correlation.

The client may supply an ``X-Request-ID`` header (on a WebSocket, also a
``request_id`` query parameter); we accept it only if it matches a strict
allowlist regex (``^[A-Za-z0-9_-]{1,64}$``) so a malicious or malformed value
cannot pollute logs (CRLF injection, log injection via long values, etc.).
Otherwise we generate a fresh UUID4.

The chosen ID is exposed to handlers via ``request.state.request_id`` and to
loggers via the ``request_id_context`` contextvar, which the logging
formatter picks up automatically.
"""

from __future__ import annotations

import contextvars
import re
import time
from urllib.parse import parse_qs
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"

# Strict allowlist for client-supplied request IDs: alphanumerics, underscore,
# hyphen, 1-64 chars. Anything else (spaces, control chars, newlines, very
# long values) is rejected and a fresh UUID is generated instead -- this
# prevents log injection and keeps log lines readable.
_CLIENT_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: Contextvar holding the current request ID, set by RequestIdMiddleware and
#: read by the logging formatter/filter so every log line for a request is
#: correlated without threading the ID through every call.
request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id_context", default=None
)


def route_path(scope: Scope) -> str:
    """The matched route's template (``/memories/documents/{topic}``), else the raw path.

    The raw path can carry the user's own words: a memory area's slug is made from its name.
    """
    template = getattr(scope.get("route"), "path", None)
    return template if isinstance(template, str) else str(scope.get("path", ""))


def client_request_id(scope: Scope) -> str | None:
    """The client's id: its header, or on a WebSocket a ``request_id`` query parameter,
    since a browser socket cannot set headers."""
    header = Headers(scope=scope).get(REQUEST_ID_HEADER)
    if header or scope["type"] != "websocket":
        return header
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    values = query.get("request_id")
    return values[0] if values else None


def _normalize_request_id(raw: str | None) -> str:
    """Return a valid request ID, generating one if *raw* is missing/invalid."""
    if raw and _CLIENT_REQUEST_ID_RE.fullmatch(raw):
        return raw
    return str(uuid4())


class RequestIdMiddleware:
    """Pure ASGI, so WebSocket connections get a request id too (Starlette's
    ``BaseHTTPMiddleware`` passed them straight through), and the access line is written
    when the response has gone out, a stream included.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        request_id = _normalize_request_id(client_request_id(scope))
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id if scope["type"] == "http" else send)
        finally:
            if scope["type"] == "http":
                # Lazy import: logging.py reads request_id_context from this module.
                from app.core.logging import log_http_request

                log_http_request(
                    method=str(scope.get("method", "")),
                    path=route_path(scope),
                    status=status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                )
            request_id_context.reset(token)
