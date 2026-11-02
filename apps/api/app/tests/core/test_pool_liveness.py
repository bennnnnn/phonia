"""Pooled connections are checked on checkout only when they may have died (core/pool_liveness).

``pool_pre_ping`` spent three round trips (BEGIN, ``;``, ROLLBACK) before the first
query of every session. Now a connection the server closed is replaced without a
round trip, one idle past the threshold is pinged first (one round trip), and one
used moments ago is trusted; a unit of work whose first statement finds one dead
anyway runs once more on a new connection. These run against the test Postgres,
where ``pg_terminate_backend`` ends a pooled connection the way Neon suspending its
compute or a restart does.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import asyncpg
import pytest
from sqlalchemy import exc, text
from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core import pool_liveness
from app.core.config import get_settings
from app.core.database_url import prepare_asyncpg_url


def _engine(*, idle_ping_seconds: float | None) -> AsyncEngine:
    """One pooled connection, so every query reuses it; None leaves the check out."""
    url, connect_args = prepare_asyncpg_url(get_settings().database_url)
    engine = create_async_engine(
        url, connect_args=connect_args, pool_size=1, max_overflow=0, pool_use_lifo=True
    )
    if idle_ping_seconds is not None:
        pool_liveness.install(engine.sync_engine, idle_ping_seconds=idle_ping_seconds)
    return engine


@pytest.fixture
async def engines() -> AsyncIterator[Callable[..., AsyncEngine]]:
    made: list[AsyncEngine] = []

    def make(*, idle_ping_seconds: float | None) -> AsyncEngine:
        made.append(_engine(idle_ping_seconds=idle_ping_seconds))
        return made[-1]

    yield make
    for engine in made:
        await engine.dispose()


@pytest.fixture
def pings(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every liveness ping sent from here on; SQLAlchemy's own three-trip ping fails the test."""
    sent: list[Any] = []
    ping = pool_liveness.ping

    def counting(driver_connection: Any) -> None:
        sent.append(driver_connection)
        ping(driver_connection)

    def pre_ping(_dbapi_connection: Any) -> bool:
        raise AssertionError("SQLAlchemy's ping was used")

    monkeypatch.setattr(pool_liveness, "ping", counting)
    monkeypatch.setattr(PGDialect_asyncpg, "do_ping", pre_ping)
    return sent


async def _backend(engine: AsyncEngine) -> tuple[int, Any]:
    """The server process behind the pooled connection, and its asyncpg connection."""
    async with engine.connect() as conn:
        pid = int((await conn.execute(text("SELECT pg_backend_pid()"))).scalar_one())
        raw = await conn.get_raw_connection()
        return pid, raw.driver_connection


async def _end_on_the_server(pid: int, driver: Any) -> None:
    """Terminate the backend from another connection and wait until asyncpg sees it."""
    dsn = make_url(get_settings().database_url).set(drivername="postgresql")
    killer = await asyncpg.connect(dsn.render_as_string(hide_password=False))
    try:
        await killer.execute("SELECT pg_terminate_backend($1)", pid)
    finally:
        await killer.close()
    for _ in range(100):
        if driver.is_closed():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("asyncpg never saw the server close the connection")


async def test_a_connection_the_server_closed_is_replaced_without_a_round_trip(
    engines, pings
) -> None:
    engine = engines(idle_ping_seconds=60)
    first, driver = await _backend(engine)
    await _end_on_the_server(first, driver)

    second, _ = await _backend(engine)

    assert second != first
    assert pings == []


async def test_without_the_check_a_closed_pooled_connection_fails_the_next_query(engines) -> None:
    """Why the check exists: with neither pre-ping nor it, the dead connection is used."""
    engine = engines(idle_ping_seconds=None)
    first, driver = await _backend(engine)
    await _end_on_the_server(first, driver)

    with pytest.raises(exc.DBAPIError):
        await _backend(engine)


async def test_a_connection_used_moments_ago_is_trusted_without_a_ping(engines, pings) -> None:
    engine = engines(idle_ping_seconds=60)

    pids = [(await _backend(engine))[0] for _ in range(3)]

    assert len(set(pids)) == 1
    assert pings == []


async def test_a_connection_idle_past_the_threshold_is_pinged_first(engines, pings) -> None:
    engine = engines(idle_ping_seconds=0.05)
    first, _ = await _backend(engine)
    await asyncio.sleep(0.1)

    second, _ = await _backend(engine)

    assert second == first
    assert len(pings) == 1


async def test_the_idle_ping_is_one_simple_query_outside_a_transaction(
    engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One message on the wire: no BEGIN or ROLLBACK, nothing prepared (PgBouncer-safe)."""
    engine = engines(idle_ping_seconds=0)
    await _backend(engine)
    sent: list[tuple[str, tuple[Any, ...], bool]] = []
    execute = asyncpg.connection.Connection.execute

    async def recording(driver: Any, query: str, *args: Any, **kwargs: Any) -> Any:
        sent.append((query, args, driver.is_in_transaction()))
        return await execute(driver, query, *args, **kwargs)

    monkeypatch.setattr(asyncpg.connection.Connection, "execute", recording)

    async with engine.connect() as conn:
        assert sent == [("SELECT 1", (), False)]
        assert (await conn.execute(text("SELECT 2"))).scalar_one() == 2


async def test_a_silently_dropped_idle_connection_fails_its_ping_and_the_pool_is_recycled(
    engines, pings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = engines(idle_ping_seconds=0)
    first, driver = await _backend(engine)
    await _end_on_the_server(first, driver)
    # A drop the driver had not heard about at checkout (a NAT or proxy idle
    # timeout); the failed ping tells it.
    unnoticed = [True]
    real = pool_liveness.server_closed

    def noticed_after_the_ping(driver_connection: Any) -> bool:
        if unnoticed:
            unnoticed.pop()
            return False
        return real(driver_connection)

    monkeypatch.setattr(pool_liveness, "server_closed", noticed_after_the_ping)

    second, _ = await _backend(engine)

    assert second != first
    assert len(pings) == 1
    assert engine.sync_engine.pool._invalidate_time > 0  # every older connection goes too


async def test_an_idle_connection_whose_ping_fails_while_open_is_replaced_alone(
    engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = engines(idle_ping_seconds=0)
    first, _ = await _backend(engine)

    def timed_out(_driver_connection: Any) -> None:
        raise TimeoutError("no answer within the command timeout")

    monkeypatch.setattr(pool_liveness, "ping", timed_out)

    second, _ = await _backend(engine)

    assert second != first
    assert engine.sync_engine.pool._invalidate_time == 0


def test_a_connection_opened_on_another_event_loop_is_replaced() -> None:
    """Each TestClient request runs on a new loop; pre-ping used to catch this too."""
    engine = _engine(idle_ping_seconds=60)
    try:
        first, _ = asyncio.run(_backend(engine))
        second, _ = asyncio.run(_backend(engine))
    finally:
        # The pooled connection's loop is gone: drop it rather than close it there.
        asyncio.run(engine.dispose(close=False))

    assert second != first


def test_the_app_engine_checks_liveness_instead_of_pinging_every_checkout() -> None:
    from app.core import db

    pool = db.engine.sync_engine.pool
    assert pool._pre_ping is False
    assert pool.dispatch.checkout
    assert get_settings().db_idle_ping_seconds > 0


# ── A unit of work whose first statement finds its connection dead ────────────


def _sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _dead_but_trusted(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> int:
    """The pooled connection's backend ended, and the checkout cannot tell (asyncpg has
    not read the close yet: an RST still on its way)."""
    pid, driver = await _backend(engine)
    await _end_on_the_server(pid, driver)
    monkeypatch.setattr(pool_liveness, "server_closed", lambda _driver: False)
    return pid


async def test_a_unit_whose_first_statement_finds_the_connection_dead_runs_again(
    engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = engines(idle_ping_seconds=60)
    dead = await _dead_but_trusted(engine, monkeypatch)
    runs: list[int] = []

    async def work(session: AsyncSession) -> int:
        runs.append(1)
        return int((await session.execute(text("SELECT pg_backend_pid()"))).scalar_one())

    pid = await pool_liveness.run_unit(_sessions(engine), work)

    assert len(runs) == 2
    assert pid != dead


async def test_without_the_retry_the_dead_connection_fails_the_unit(
    engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Why ``run_unit`` exists: the first statement on it raises."""
    engine = engines(idle_ping_seconds=60)
    await _dead_but_trusted(engine, monkeypatch)

    with pytest.raises(exc.DBAPIError) as raised:
        async with _sessions(engine)() as session:
            await session.execute(text("SELECT 1"))

    assert raised.value.connection_invalidated


async def test_a_unit_that_already_ran_a_statement_is_never_run_again(
    engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Something may already be written: the error is the caller's."""
    engine = engines(idle_ping_seconds=60)
    runs: list[int] = []

    async def work(session: AsyncSession) -> None:
        runs.append(1)
        pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        raw = await (await session.connection()).get_raw_connection()
        await _end_on_the_server(int(pid), raw.driver_connection)
        await session.execute(text("SELECT 1"))

    with pytest.raises(exc.DBAPIError) as raised:
        await pool_liveness.run_unit(_sessions(engine), work)

    assert raised.value.connection_invalidated
    assert runs == [1]


async def test_a_unit_that_fails_for_another_reason_is_never_run_again(engines) -> None:
    engine = engines(idle_ping_seconds=60)
    runs: list[int] = []

    async def work(session: AsyncSession) -> None:
        runs.append(1)
        await session.execute(text("SELECT * FROM no_such_table_here"))

    with pytest.raises(exc.ProgrammingError):
        await pool_liveness.run_unit(_sessions(engine), work)

    assert runs == [1]


async def test_a_unit_that_dies_twice_raises_the_second_failure(
    engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = engines(idle_ping_seconds=60)
    await _dead_but_trusted(engine, monkeypatch)
    runs: list[int] = []

    async def work(session: AsyncSession) -> None:
        runs.append(1)
        if len(runs) == 2:
            # The new connection dies before its first statement too.
            raw = await (await session.connection()).get_raw_connection()
            driver = raw.driver_connection
            assert driver is not None
            pid = await driver.fetchval("SELECT pg_backend_pid()")
            await _end_on_the_server(int(pid), driver)
        await session.execute(text("SELECT 1"))

    with pytest.raises(exc.DBAPIError):
        await pool_liveness.run_unit(_sessions(engine), work)

    assert len(runs) == 2
