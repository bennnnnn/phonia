"""Per-chat registry of in-flight turn finalization tasks.

The chat routers send `done` to the client as soon as the token stream ends,
while the DB commit (assistant message insert, usage, quota) finishes in a
background task. Anything that reads a chat's messages right after a turn —
the next turn's prompt build, regenerate/edit, message feedback — must await
that pending commit first or it can miss the just-streamed assistant reply.

The WS stream producer is tracked separately (``_inflight``). GET /messages
waits on it so a New-chat leave can still return the completed assistant.
``stream_chat_response`` must *not* wait on that producer: it registers the
producer, then ``asyncio.gather``s the finalize wait as a *child* Task, so
``current_task() is producer`` is false and a shared map deadlocks 10s.

Same-process waiters use an in-memory task map. Cross-process / multi-instance
waiters also poll a short-lived Redis marker set when finalize is registered
and cleared when the DB task finishes.

Each producer may carry its transport's Stop. When the server is told to stop
(``core.shutdown``), ``stop_inflight_streams`` runs every one, so partial replies
are saved and locks released inside the graceful window instead of dying with
the machine.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from uuid import UUID

from redis.asyncio import Redis

from app.exceptions import ChatBusyError, RedisUnavailableError

logger = logging.getLogger(__name__)

_FINALIZE_WAIT_TIMEOUT_SECONDS = 10.0
# A finalize commit takes well under a second; the TTL only matters when the
# machine died before clearing it, and then every send on the chat is busy.
_FINALIZE_MARKER_TTL_SECONDS = 30
_FINALIZE_POLL_INTERVAL_SECONDS = 0.05

_pending: dict[UUID, asyncio.Task[None]] = {}
_inflight: dict[UUID, asyncio.Task[None]] = {}
_stops: dict[asyncio.Task[None], Callable[[], None]] = {}


def _marker_key(chat_id: UUID) -> str:
    return f"chatfinal:{chat_id}"


def _track(store: dict[UUID, asyncio.Task[None]], chat_id: UUID, task: asyncio.Task[None]) -> None:
    store[chat_id] = task

    def _clear(done: asyncio.Task[None]) -> None:
        if store.get(chat_id) is done:
            store.pop(chat_id, None)

    task.add_done_callback(_clear)


async def _await_bounded(task: asyncio.Task[None], *, timeout_log: str) -> None:
    try:
        await asyncio.wait_for(asyncio.shield(task), _FINALIZE_WAIT_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning(timeout_log)
    except Exception:
        with contextlib.suppress(Exception):
            logger.debug("In-flight chat task failed", exc_info=True)


def register_pending_finalize(chat_id: UUID, task: asyncio.Task[None]) -> None:
    """Track `task` as the chat's in-flight finalize; auto-clears on completion."""
    _track(_pending, chat_id, task)


def register_inflight_stream(
    chat_id: UUID,
    task: asyncio.Task[None],
    *,
    stop: Callable[[], None] | None = None,
) -> None:
    """Track the WS/SSE producer so GET /messages can wait out a New-chat leave.

    ``stop`` is the transport's own Stop for this turn (``stop_inflight_streams``).
    """
    _track(_inflight, chat_id, task)
    if stop is not None:
        _stops[task] = stop
        task.add_done_callback(lambda done: _stops.pop(done, None))


def stop_inflight_streams() -> int:
    """Stop every turn still producing, as the user's Stop would; returns how many.

    The server is shutting down: each partial reply is saved (marked interrupted),
    the turn's quota settles and its prepare lock is released before the process exits.
    """
    stops = [stop for task, stop in list(_stops.items()) if not task.done()]
    for stop in stops:
        try:
            stop()
        except Exception:
            logger.exception("Stopping an in-flight chat stream failed")
    if stops:
        logger.info("Stopped %d in-flight chat stream(s) for shutdown", len(stops))
    return len(stops)


async def mark_pending_finalize(redis: Redis, chat_id: UUID) -> None:
    """Publish a cross-process "finalize in flight" marker for ``chat_id``."""
    try:
        await redis.set(_marker_key(chat_id), "1", ex=_FINALIZE_MARKER_TTL_SECONDS)
    except Exception:
        logger.debug("Failed to mark pending finalize chat_id=%s", chat_id, exc_info=True)


async def clear_pending_finalize(redis: Redis, chat_id: UUID) -> None:
    """Clear the cross-process finalize marker after commit attempt finishes."""
    try:
        await redis.delete(_marker_key(chat_id))
    except Exception:
        logger.debug("Failed to clear pending finalize chat_id=%s", chat_id, exc_info=True)


async def wait_for_inflight_stream(chat_id: UUID) -> None:
    """Wait (bounded) for this process's WS/SSE producer. Never used by the producer."""
    task = _inflight.get(chat_id)
    if task is None or task.done():
        return
    await _await_bounded(
        task,
        timeout_log=f"In-flight stream still running after wait chat_id={chat_id}",
    )


async def wait_for_pending_finalize(
    chat_id: UUID,
    redis: Redis | None = None,
    *,
    require_complete: bool = False,
) -> None:
    """Wait (bounded) for the chat's previous turn to finish committing.

    History reads may return the last committed snapshot after the bounded
    wait. A new turn requires completion so its prompt and writes cannot race
    the previous assistant insert; timeout returns a retriable busy error.
    A failed finalize has finished and logs its own failure.
    """
    task = _pending.get(chat_id)
    if task is not None and not task.done():
        await _await_bounded(
            task,
            timeout_log=f"Pending turn finalize still running after wait chat_id={chat_id}",
        )
        if require_complete and not task.done():
            raise ChatBusyError("Still saving the previous response. Please retry shortly.")
        return

    if redis is None:
        return

    # Another API machine may own the finalize task — poll the Redis marker.
    deadline = time.monotonic() + _FINALIZE_WAIT_TIMEOUT_SECONDS
    try:
        while time.monotonic() < deadline:
            if not await redis.exists(_marker_key(chat_id)):
                return
            await asyncio.sleep(_FINALIZE_POLL_INTERVAL_SECONDS)
    except Exception as exc:
        logger.debug("Pending finalize Redis wait failed chat_id=%s", chat_id, exc_info=True)
        if require_complete:
            raise RedisUnavailableError() from exc
        return
    logger.warning("Pending turn finalize marker still set after wait chat_id=%s", chat_id)
    if require_complete:
        raise ChatBusyError("Still saving the previous response. Please retry shortly.")
