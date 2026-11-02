"""Check a pooled Postgres connection on checkout only when it may have died idle,
and run a unit of work once more when its first statement finds one dead anyway.

``pool_pre_ping`` pinged on every checkout: with asyncpg that is BEGIN, ``;`` and
ROLLBACK, three round trips (about 36 ms from Fly to Neon) before a session's
first query, and a chat turn opens several sessions before the model is called.
A connection used moments ago is almost always alive, so on checkout:

- one the server already closed (Neon suspending the compute, a pooler or Postgres
  restart, ``pg_terminate_backend``) is replaced at no cost: asyncpg saw the close.
  So is one opened on another event loop, which cannot be used on this one (each
  ``TestClient`` request runs on a new loop; the app itself has one);
- one idle for ``idle_ping_seconds`` or longer is pinged first (``ping``, one round
  trip), since it may have been dropped without a word (a NAT or proxy idle
  timeout). One that fails is replaced; when the driver then reports it closed,
  every connection opened before it is recycled too, as pre-ping did;
- any other is trusted. If it died anyway and asyncpg has not seen the close yet,
  its first statement fails and SQLAlchemy recycles every connection older than
  the failure. ``run_unit`` runs that unit of work once more on a new connection:
  a chat turn's reads and the saves of its message and reply go through it. Any
  other request answers 503 + Retry-After (``core/unavailable``), which the phone
  does not retry by itself.

The pool also hands out the connection returned last (``pool_use_lifo`` in
``core/db``), so busy connections stay warm and spare ones age into the ping or
the recycle instead of every connection taking turns.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import event, exc
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import ConnectionPoolEntry, PoolProxiedConnection
from sqlalchemy.util import await_only

logger = logging.getLogger(__name__)

_CHECKED_IN_AT = "checked_in_at"


def server_closed(driver_connection: Any) -> bool:
    """True when the driver already knows the server ended this connection."""
    is_closed = getattr(driver_connection, "is_closed", None)
    return bool(is_closed()) if callable(is_closed) else False


def opened_on_another_loop(driver_connection: Any) -> bool:
    """True for an asyncpg connection bound to an event loop other than the running one."""
    loop = getattr(driver_connection, "_loop", None)
    try:
        return loop is not None and loop is not asyncio.get_running_loop()
    except RuntimeError:  # no running loop: nothing to compare with
        return False


def ping(driver_connection: Any) -> None:
    """One round trip: ``SELECT 1`` as a simple query, outside any transaction.

    SQLAlchemy's asyncpg ping wraps ``fetchrow(";")`` in BEGIN and ROLLBACK (three
    round trips) so that PgBouncer's transaction mode keeps the statement's prepare
    and execute on one server connection. A simple query is a single message with
    nothing to prepare, so it needs no transaction. (asyncpg's simple query cannot
    take an empty one: ``;`` fails on the missing command tag.)
    """
    await_only(driver_connection.execute("SELECT 1"))


def install(engine: Engine, *, idle_ping_seconds: float) -> None:
    """Check ``engine``'s connections on checkout as above; 0 pings every reuse."""

    @event.listens_for(engine, "checkin")
    def _note_checkin(_dbapi_connection: Any, record: ConnectionPoolEntry) -> None:
        record.info[_CHECKED_IN_AT] = time.monotonic()

    @event.listens_for(engine, "checkout")
    def _check_liveness(
        _dbapi_connection: Any, record: ConnectionPoolEntry, _proxy: PoolProxiedConnection
    ) -> None:
        driver = record.driver_connection
        if server_closed(driver) or opened_on_another_loop(driver):
            raise exc.DisconnectionError("Pooled connection can no longer be used")
        checked_in_at = record.info.get(_CHECKED_IN_AT)
        if checked_in_at is None or time.monotonic() - checked_in_at < idle_ping_seconds:
            # Just opened, or used moments ago.
            return
        try:
            ping(driver)
        except Exception as error:
            if server_closed(driver):
                # Dropped by the server or the network: older connections likely were too.
                raise exc.InvalidatePoolError("Ping after idle failed") from error
            raise exc.DisconnectionError("Ping after idle failed") from error


# Statements that succeeded in the running ``run_unit``; None outside one.
_SUCCEEDED: ContextVar[list[int] | None] = ContextVar("unit_statements_succeeded", default=None)


@event.listens_for(Engine, "after_cursor_execute")
def _note_statement(*_args: Any) -> None:
    succeeded = _SUCCEEDED.get()
    if succeeded is not None:
        succeeded[0] += 1


async def run_unit[T](
    open_session: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    work: Callable[[AsyncSession], Awaitable[T]],
) -> T:
    """Run ``work`` in a session from ``open_session``; once more in a new one when
    its first statement found the pooled connection dead.

    Only a unit none of whose statements succeeded runs again, so nothing is written
    twice: its transaction ended with the connection before anything was committed.
    The failure already recycled that connection and every older one, so the second
    run gets a new connection. Any other error is raised as it was.
    """
    succeeded = [0]
    token = _SUCCEEDED.set(succeeded)
    try:
        try:
            async with open_session() as session:
                return await work(session)
        except exc.DBAPIError as error:
            if not error.connection_invalidated or succeeded[0]:
                raise
            logger.warning(
                "Pooled connection was dead at a unit's first statement; running it again"
            )
        async with open_session() as session:
            return await work(session)
    finally:
        _SUCCEEDED.reset(token)
