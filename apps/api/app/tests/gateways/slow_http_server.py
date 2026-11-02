"""A local HTTP server that drips its reply, for deadline tests.

It answers every request with headers at once, then one body byte every
``drip_seconds``: each read finishes well inside a per-read timeout, so only an
overall deadline can end the fetch. With ``redirects``, the first hops answer
302 to the next path (``/1``, ``/2``, …) after the same delay.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

_BODY_LENGTH = 100_000

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


def _hop_of(path: str) -> int:
    last = path.rsplit("/", 1)[-1]
    return int(last) if last.isdigit() else 0


def _drip_handler(drip_seconds: float, redirects: int) -> Handler:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            hop = _hop_of(head.decode("latin-1").split(" ", 2)[1])
            if hop < redirects:
                await asyncio.sleep(drip_seconds)
                writer.write(
                    f"HTTP/1.1 302 Found\r\nLocation: /{hop + 1}\r\n"
                    "Content-Length: 0\r\n\r\n".encode()
                )
                await writer.drain()
                return
            writer.write(
                "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                f"Content-Length: {_BODY_LENGTH}\r\n\r\n".encode()
            )
            await writer.drain()
            for _ in range(_BODY_LENGTH):
                writer.write(b"a")
                await writer.drain()
                await asyncio.sleep(drip_seconds)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    return handle


@asynccontextmanager
async def dripping_server(*, drip_seconds: float = 0.2, redirects: int = 0) -> AsyncIterator[int]:
    """Serve on 127.0.0.1; yields the port."""
    server = await asyncio.start_server(
        _drip_handler(drip_seconds, redirects), host="127.0.0.1", port=0
    )
    port = int(server.sockets[0].getsockname()[1])
    try:
        yield port
    finally:
        server.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(server.wait_closed(), timeout=1.0)
