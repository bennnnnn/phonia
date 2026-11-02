"""Refuse oversized HTTP request bodies before a route buffers them.

FastAPI reads a JSON body into memory before dependencies (auth, rate limits)
run, and routes that call ``request.body()`` read a chunked upload to the end
before checking its length. Without a cap, one anonymous request can push
hundreds of megabytes into a 512 MB machine.

The cap is enforced twice: a declared ``Content-Length`` over the limit is
answered with 413 before any byte is read, and a body without one (chunked)
is counted as it streams and stopped one chunk past the limit. A few routes
legitimately take photos and audio; the app factory passes their path
patterns as ``upload_paths`` so this module never imports a product module.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings

TOO_LARGE_DETAIL = "Request body too large"


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers") or []:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class RequestBodyLimitMiddleware:
    """Pure ASGI middleware (no BaseHTTPMiddleware buffering)."""

    def __init__(self, app: ASGIApp, *, upload_paths: Iterable[str] = ()) -> None:
        self.app = app
        self._upload_paths = tuple(re.compile(pattern) for pattern in upload_paths)

    def _limit_for(self, path: str) -> int:
        settings = get_settings()
        if any(pattern.fullmatch(path) for pattern in self._upload_paths):
            return settings.max_upload_request_body_bytes
        return settings.max_request_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit_for(str(scope.get("path") or ""))
        if limit <= 0:
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _too_large(scope, receive, send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # FastAPI re-raises HTTPException from body parsing, and a
                    # route's own ``request.body()`` lets it propagate to the
                    # exception middleware, so this becomes a 413 response.
                    raise HTTPException(status_code=413, detail=TOO_LARGE_DETAIL)
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except HTTPException as exc:
            if exc.status_code != 413 or response_started:
                raise
            await _too_large(scope, receive, send)


async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
    response = JSONResponse({"detail": TOO_LARGE_DETAIL}, status_code=413)
    await response(scope, receive, send)
