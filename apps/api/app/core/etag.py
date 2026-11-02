"""Weak ETags for the lists the phone reads again (code-health audit NET-16).

The phone downloaded its whole to-do list, chat list and the open chat's newest
messages on every return to the app, whether or not anything had changed. Such a
reply now carries a weak ETag, a hash of its body; a request that sends it back in
``If-None-Match`` is answered ``304 Not Modified``, with no body.
"""

from __future__ import annotations

import hashlib

from fastapi import Request, Response
from pydantic import BaseModel

# The phone keeps the body and asks again each time (never a stale copy from a cache).
_CACHE_CONTROL = "private, no-cache"


def body_etag(body: bytes) -> str:
    return f'W/"{hashlib.sha256(body).hexdigest()[:32]}"'


def _opaque(tag: str) -> str:
    # Weak comparison: W/"x" and "x" name the same body.
    return tag.strip().removeprefix("W/")


def _client_has(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    tags = [tag for tag in if_none_match.split(",") if tag.strip()]
    return any(tag.strip() == "*" or _opaque(tag) == _opaque(etag) for tag in tags)


def conditional_json(request: Request, payload: BaseModel) -> Response:
    """``payload`` as JSON with its ETag, or a 304 when the client already holds it."""
    body = payload.model_dump_json().encode()
    etag = body_etag(body)
    headers = {"ETag": etag, "Cache-Control": _CACHE_CONTROL}
    if _client_has(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
