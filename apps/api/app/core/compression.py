"""gzip for the JSON and text the API answers with.

Fly's proxy passes bodies through as they are, so every list the phone reads (a
chat's messages, memory, to-dos, the drawer) crossed the network uncompressed:
about 168 KB for one account's everyday reads that gzip sends in about 35 KB.
The phone's HTTP stack (NSURLSession, OkHttp) asks for gzip and inflates it
itself; nothing in the app changes.

What is left alone: an event stream (SSE replies must reach the phone token by
token, and Starlette's own exclusion keeps them that way), WebSockets (not HTTP
responses), bodies already compressed or binary (photos, files, audio), bodies
under ``minimum_size``, read-aloud audio (base64, it barely shrinks), and the
responses that carry credentials (sign-in, refresh, the live-talk secret): a
secret is never compressed beside text an attacker could choose (BREACH).
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipResponder
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Bodies worth compressing; everything else (images, PDFs, audio) is sent as is.
_COMPRESSIBLE_TYPES = ("application/json", "text/plain", "text/html", "text/markdown", "text/csv")

# Never compressed. Replies that hold a token or a client secret; and read-aloud audio,
# base64 in JSON, which gzip shrinks by a quarter for about 11 ms of event-loop CPU a clip.
UNCOMPRESSED_PATHS = frozenset(
    {
        "/auth/google",
        "/auth/apple",
        "/auth/dev",
        "/auth/refresh",
        "/speech/live/session",
        "/speech/tts",
    }
)

# zlib's default: within 2 % of level 9 on the API's lists, at about half the CPU.
_COMPRESS_LEVEL = 6
_MINIMUM_SIZE = 500


class _TextGZipResponder(GZipResponder):
    """Starlette's responder, compressing only the types above.

    Starlette compresses every type but ``text/event-stream``; this widens that
    exclusion to every type not listed, and to a small body that arrives in parts
    (``RestRateLimitMiddleware`` re-streams every reply, so Starlette's own size
    check, which reads only a whole body, never ran). ``test_compression.py``
    holds both.
    """

    async def send_with_compression(self, message: Message) -> None:
        await super().send_with_compression(message)
        if message["type"] == "http.response.start":
            headers = Headers(raw=message["headers"])
            declared = headers.get("content-length")
            small = (
                declared is not None and declared.isdigit() and int(declared) < self.minimum_size
            )
            if small or not headers.get("content-type", "").startswith(_COMPRESSIBLE_TYPES):
                self.content_type_is_excluded = True


class CompressionMiddleware:
    """gzip a JSON or text response for a client that accepts it."""

    def __init__(self, app: ASGIApp, *, minimum_size: int = _MINIMUM_SIZE) -> None:
        self._app = app
        self._minimum_size = minimum_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["path"] in UNCOMPRESSED_PATHS
            or "gzip" not in Headers(scope=scope).get("accept-encoding", "")
        ):
            await self._app(scope, receive, send)
            return
        responder = _TextGZipResponder(self._app, self._minimum_size, compresslevel=_COMPRESS_LEVEL)
        await responder(scope, receive, send)
