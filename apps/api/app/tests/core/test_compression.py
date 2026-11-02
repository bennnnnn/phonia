"""gzip for JSON and text replies; streams, sockets, binaries and credentials untouched."""

from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.testclient import TestClient
from starlette.types import Message

from app.core.compression import UNCOMPRESSED_PATHS, CompressionMiddleware
from app.main import create_app
from app.modules.chat.stream_api import _sse_response

_BIG = {"messages": [{"id": i, "content": "a reply the phone shows " * 8} for i in range(40)]}
_JPEG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 40


def _mini_app() -> FastAPI:
    app = FastAPI()

    @app.get("/big")
    async def big() -> JSONResponse:
        return JSONResponse(_BIG)

    @app.get("/small")
    async def small() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.get("/photo")
    async def photo() -> Response:
        return Response(content=_JPEG, media_type="image/jpeg")

    @app.post("/auth/refresh")
    async def refresh() -> JSONResponse:
        return JSONResponse({"access_token": "secret" * 200})

    @app.websocket("/ws")
    async def socket(websocket: WebSocket) -> None:
        await websocket.accept()
        frame = await websocket.receive_json()
        await websocket.send_json({"echo": frame, "pad": "x" * 2000})
        await websocket.close()

    app.add_middleware(CompressionMiddleware)
    return app


@pytest.mark.parametrize(
    ("path", "accept", "encoded"),
    [
        ("/big", "gzip, deflate, br", True),
        ("/big", "identity", False),
        ("/small", "gzip", False),
        ("/photo", "gzip", False),
    ],
)
def test_compression_by_body(path: str, accept: str, encoded: bool) -> None:
    client = TestClient(_mini_app())
    response = client.get(path, headers={"Accept-Encoding": accept})
    assert response.status_code == 200
    assert (response.headers.get("content-encoding") == "gzip") is encoded
    if path == "/big":
        # The client sees the same JSON either way.
        assert response.json() == _BIG
    if path == "/photo":
        assert response.content == _JPEG


def test_compression_shrinks_a_json_list() -> None:
    client = TestClient(_mini_app())
    raw = client.get("/big", headers={"Accept-Encoding": "identity"})
    zipped = client.get("/big", headers={"Accept-Encoding": "gzip"})
    assert zipped.num_bytes_downloaded * 5 < raw.num_bytes_downloaded
    assert zipped.headers["vary"] == "Accept-Encoding"


def test_compression_never_touches_a_credential_reply() -> None:
    assert {"/auth/refresh", "/speech/live/session"} <= UNCOMPRESSED_PATHS
    client = TestClient(_mini_app())
    response = client.post("/auth/refresh", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in response.headers
    assert response.json()["access_token"].startswith("secret")


def test_compression_lets_a_websocket_through() -> None:
    client = TestClient(_mini_app())
    with client.websocket_connect("/ws", headers={"Accept-Encoding": "gzip"}) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["echo"] == {"type": "ping"}


async def _drive(app: Any, path: str, sent: list[Message], method: str = "GET") -> None:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"t"), (b"accept-encoding", b"gzip, deflate, br")],
        "client": ("127.0.0.1", 1),
        "server": ("t", 80),
    }
    requested = False

    async def receive() -> Message:
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)


async def test_compression_streams_sse_through_the_real_stack_token_by_token() -> None:
    """The production stack (rate limit, request id, CORS, security headers, gzip) on the
    production SSE response: each event leaves as it is made, uncompressed."""
    app = create_app()
    sent: list[Message] = []
    released = asyncio.Event()

    async def events() -> AsyncIterator[str]:
        yield 'data: {"type": "start"}\n\n'
        # The next event waits until the first has reached the client.
        await released.wait()
        for word in ("Hello", " there"):
            yield f'data: {{"type": "token", "content": "{word}"}}\n\n'
        yield 'data: {"type": "done"}\n\n'

    @app.get("/test-sse")
    async def sse() -> StreamingResponse:
        return _sse_response(events())

    task = asyncio.create_task(_drive(app, "/test-sse", sent))
    for _ in range(200):
        if any(m["type"] == "http.response.body" and m.get("body") for m in sent):
            break
        await asyncio.sleep(0.01)
    first = [m for m in sent if m["type"] == "http.response.body" and m.get("body")]
    assert first and first[0]["body"] == b'data: {"type": "start"}\n\n'
    released.set()
    await asyncio.wait_for(task, 5)

    start = next(m for m in sent if m["type"] == "http.response.start")
    headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    assert headers["content-type"].startswith("text/event-stream")
    assert "content-encoding" not in headers
    bodies = [m["body"] for m in sent if m["type"] == "http.response.body" and m.get("body")]
    assert [json.loads(b.decode().removeprefix("data: "))["type"] for b in bodies] == [
        "start",
        "token",
        "token",
        "done",
    ]


async def test_compression_gzips_json_through_the_real_stack() -> None:
    """The BaseHTTPMiddleware rate limiter re-streams every reply; a big JSON one is
    still gzipped and a small one is not."""
    app = create_app()

    @app.get("/test-big")
    async def big() -> JSONResponse:
        return JSONResponse(_BIG)

    @app.get("/test-small")
    async def small() -> JSONResponse:
        return JSONResponse({"ok": True})

    for path, encoded in (("/test-big", True), ("/test-small", False)):
        sent: list[Message] = []
        await _drive(app, path, sent)
        start = next(m for m in sent if m["type"] == "http.response.start")
        headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
        assert (headers.get("content-encoding") == "gzip") is encoded
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        decoded = gzip.decompress(body) if encoded else body
        assert json.loads(decoded) == (_BIG if encoded else {"ok": True})
