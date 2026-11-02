"""A route's own body cap, below the app-wide one in ``body_limit``."""

from fastapi import HTTPException, Request, status


def reject_oversized(request: Request, body: bytes, max_bytes: int, detail: str) -> None:
    """413 when the declared Content-Length or the body read so far is over ``max_bytes``.

    Call it with ``b""`` before reading, so a declared oversized body is refused unread.
    """
    declared = request.headers.get("content-length")
    try:
        too_long = declared is not None and int(declared) > max_bytes
    except ValueError:
        too_long = False
    if too_long or len(body) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=detail)
