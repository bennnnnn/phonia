"""Per-socket limits on the chat WebSocket: frames, sockets per user, idle time.

All three are in-process: they count this machine's sockets. With more than one
``app`` machine a user can hold the socket cap on each one (docs/PRODUCTION.md,
"Load and abuse limits"). The connect and handshake limits are in Redis
(``ws_api``).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from app.exceptions import RATE_LIMITED_CODE

# Every frame after auth counts, chargeable or not. Only message/regenerate
# were limited (30/min, account-wide); pings, cancels, unknown types and bad
# JSON were unlimited, and each bad frame was parsed and answered. The app
# sends at most a message plus a cancel per turn, so 120/min per socket is
# far above real use. In-process: the budget belongs to one socket.
WS_FRAME_LIMIT = 120
WS_FRAME_WINDOW_SECONDS = 60.0
WS_FRAME_FLOOD_PAYLOAD = {
    "type": "error",
    "code": RATE_LIMITED_CODE,
    "message": "Too many messages. Reconnect in a minute.",
}
# Close codes the phone reads (features/chat/model/wsTransport.ts). No error
# frame goes first: with no turn open, the phone would show it as a chat error.
# Idle between turns: the phone opens a new socket on its next send.
WS_IDLE_CLOSE_CODE = 4408
# Over the per-user cap: the phone sends over SSE instead.
WS_TOO_MANY_SOCKETS_CLOSE_CODE = 4429

# Open chat sockets per user on this machine.
_open_sockets: dict[UUID, int] = {}


class FrameBudget:
    """Fixed-window frame counter for one socket."""

    def __init__(self) -> None:
        self._window_start = time.monotonic()
        self._count = 0

    def allow(self) -> bool:
        now = time.monotonic()
        if now - self._window_start >= WS_FRAME_WINDOW_SECONDS:
            self._window_start = now
            self._count = 0
        self._count += 1
        return self._count <= WS_FRAME_LIMIT


async def safe_send_json(websocket: WebSocket, payload: dict[str, Any]) -> bool:
    """Send a WS frame; return False if the client already disconnected."""
    try:
        await websocket.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


async def close_flooding_socket(websocket: WebSocket) -> None:
    await safe_send_json(websocket, WS_FRAME_FLOOD_PAYLOAD)
    with suppress(Exception):
        await websocket.close(code=1008)


async def close_quietly(websocket: WebSocket, code: int) -> None:
    """Close with ``code`` and no error frame (see the close codes above)."""
    with suppress(Exception):
        await websocket.close(code=code)


async def receive_frame(
    websocket: WebSocket, idle_seconds: float, pending: asyncio.Task[Any] | None = None
) -> Any:
    """The next JSON frame; ``TimeoutError`` after ``idle_seconds`` without one (0: no limit).

    ``pending`` is the read a turn left running when it ended first: its frame is the next
    one. A read is cancelled only once nothing more is read from the socket (idle close,
    shutdown): a server may lose the frame it was handing that read, as Starlette's test
    client does, and the socket would then never answer it (2026-11-01).
    """
    read = pending if pending is not None else asyncio.create_task(websocket.receive_json())
    try:
        done, _ = await asyncio.wait({read}, timeout=idle_seconds or None)
    except BaseException:
        read.cancel()
        raise
    if not done:
        read.cancel()
        with suppress(asyncio.CancelledError):
            await read
        raise TimeoutError
    return read.result()


@contextmanager
def user_socket_slot(user_id: UUID, limit: int) -> Iterator[bool]:
    """Hold one of ``user_id``'s sockets on this machine; False when ``limit`` are open.

    ``limit`` 0 disables the cap.
    """
    held = _open_sockets.get(user_id, 0)
    if limit > 0 and held >= limit:
        yield False
        return
    _open_sockets[user_id] = held + 1
    try:
        yield True
    finally:
        remaining = _open_sockets.get(user_id, 1) - 1
        if remaining > 0:
            _open_sockets[user_id] = remaining
        else:
            _open_sockets.pop(user_id, None)


def open_socket_count() -> int:
    """Chat sockets open on this machine (saturation report)."""
    return sum(_open_sockets.values())
