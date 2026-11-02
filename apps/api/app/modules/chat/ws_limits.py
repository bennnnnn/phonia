"""Per-socket limits on the chat WebSocket: frames, sockets per user, idle time.

The frame budget and the idle timer belong to one socket, so they are in-process.
Sockets per user are counted across every ``app`` machine in Redis
(``user_socket_slot``): counted per machine, a user could hold the cap on each.
The connect and handshake limits are in Redis too (``ws_api``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.exceptions import RATE_LIMITED_CODE
from app.modules.chat.stream_events import RATE_LIMITED_MESSAGE

logger = logging.getLogger(__name__)

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
# A socket's refusal of a frame or a connection, outside a turn's own frames: its sign-in,
# a frame it cannot read, its connect limit. Each names a code; the phone matched the
# English "Unauthorized" (features/chat/model/wsTransport.ts reads the code).
SocketRefusal = Literal[
    "unauthorized",
    "missing_token",
    "auth_timeout",
    "invalid_json",
    "invalid_message",
    "invalid_regenerate",
    "rate_limited",
]
_INVALID_FRAME = "invalid"
_SOCKET_REFUSALS: dict[SocketRefusal, tuple[str, str]] = {
    "unauthorized": ("unauthorized", "Unauthorized"),
    "missing_token": ("missing_token", "Missing token"),
    "auth_timeout": ("auth_timeout", "Auth timeout"),
    "invalid_json": (_INVALID_FRAME, "Invalid JSON"),
    "invalid_message": (_INVALID_FRAME, "Invalid message"),
    "invalid_regenerate": (_INVALID_FRAME, "Invalid regenerate request"),
    # Over the connect limit: no turn to name.
    "rate_limited": (RATE_LIMITED_CODE, RATE_LIMITED_MESSAGE),
}


def socket_error_payload(refusal: SocketRefusal) -> dict[str, Any]:
    """The error frame for a socket's refusal: its code and the English."""
    code, message = _SOCKET_REFUSALS[refusal]
    return {"type": "error", "code": code, "message": message}


# Close codes the phone reads (features/chat/model/wsTransport.ts). No error
# frame goes first: with no turn open, the phone would show it as a chat error.
# Idle between turns: the phone opens a new socket on its next send.
WS_IDLE_CLOSE_CODE = 4408
# Over the per-user cap: the phone sends over SSE instead.
WS_TOO_MANY_SOCKETS_CLOSE_CODE = 4429

# Open chat sockets per user on this machine (the saturation report); the cap is
# counted in Redis across machines.
_open_sockets: dict[UUID, int] = {}
# Each open socket holds a lease in ``wssock:{user}`` (a sorted set: socket id ->
# expiry). The socket renews it while open; a machine that dies stops renewing, and
# its sockets stop counting within the lease, so a crash never leaks a slot.
SOCKET_LEASE_SECONDS = 90
SOCKET_RENEW_SECONDS = 30
_SOCKETS_KEY_PREFIX = "wssock:"


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


def sockets_key(user_id: UUID) -> str:
    return f"{_SOCKETS_KEY_PREFIX}{user_id}"


@asynccontextmanager
async def user_socket_slot(redis: Redis, user_id: UUID, limit: int) -> AsyncIterator[bool]:
    """Hold one of ``user_id``'s chat sockets across all machines; False when ``limit``
    are open, or when Redis cannot say (fail closed: the phone sends over SSE).

    ``limit`` 0 disables the cap (no Redis).
    """
    socket_id = uuid4().hex
    key = sockets_key(user_id)
    if limit > 0:
        try:
            admitted = await _claim_socket(redis, key, socket_id, limit)
        except Exception as exc:
            logger.warning("Chat socket count unavailable; refusing user_id=%s: %r", user_id, exc)
            admitted = False
        if not admitted:
            yield False
            return
    _open_sockets[user_id] = _open_sockets.get(user_id, 0) + 1
    renew = (
        asyncio.create_task(_renew_socket(redis, key, socket_id), name="ws_socket_lease")
        if limit > 0
        else None
    )
    try:
        yield True
    finally:
        remaining = _open_sockets.get(user_id, 1) - 1
        if remaining > 0:
            _open_sockets[user_id] = remaining
        else:
            _open_sockets.pop(user_id, None)
        if renew is not None:
            renew.cancel()
            with suppress(RedisError, OSError):  # the lease expires on its own
                await asyncio.shield(redis.zrem(key, socket_id))


async def _claim_socket(redis: Redis, key: str, socket_id: str, limit: int) -> bool:
    """Drop expired leases, add this one, count: one transaction. Over the cap, take it back."""
    now = time.time()
    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, "-inf", now)
        pipe.zadd(key, {socket_id: now + SOCKET_LEASE_SECONDS})
        pipe.zcard(key)
        pipe.expire(key, SOCKET_LEASE_SECONDS)
        _dropped, _added, held, _ttl = await pipe.execute()
    if int(held) <= limit:
        return True
    await redis.zrem(key, socket_id)
    return False


async def _renew_socket(redis: Redis, key: str, socket_id: str) -> None:
    """Keep this socket's lease (and the key) alive while the socket is open."""
    while True:
        await asyncio.sleep(SOCKET_RENEW_SECONDS)
        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.zadd(key, {socket_id: time.time() + SOCKET_LEASE_SECONDS}, xx=True)
                pipe.expire(key, SOCKET_LEASE_SECONDS)
                await pipe.execute()
        except (RedisError, OSError):
            logger.debug("Chat socket lease renew failed", exc_info=True)


def open_socket_count() -> int:
    """Chat sockets open on this machine (saturation report)."""
    return sum(_open_sockets.values())
