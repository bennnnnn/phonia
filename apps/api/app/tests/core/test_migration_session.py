"""Migrations wait at most lock_timeout for a lock, then fail instead of queueing everyone.

``ALTER TABLE users`` (0106, 0107, 0110, 0111) needs ACCESS EXCLUSIVE. Queued
behind a long query (an account delete is one cascading DELETE), it made every
later query on users wait behind it; no migration set a lock_timeout except 0103.
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, pool, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.database_url import prepare_asyncpg_url
from app.core.migration_session import bound_migration_waits


def _engine():
    url, connect_args = prepare_asyncpg_url(get_settings().database_url)
    return create_async_engine(url, poolclass=pool.NullPool, connect_args=connect_args)


async def test_each_migration_transaction_gets_the_local_timeouts() -> None:
    engine = _engine()
    bound_migration_waits(engine.sync_engine, lock_timeout="5s", statement_timeout="4min")
    try:
        async with engine.connect() as conn:
            async with conn.begin():
                lock = (await conn.execute(text("SHOW lock_timeout"))).scalar()
                statement = (await conn.execute(text("SHOW statement_timeout"))).scalar()
            async with conn.begin():
                again = (await conn.execute(text("SHOW lock_timeout"))).scalar()
    finally:
        await engine.dispose()
    assert (lock, statement, again) == ("5s", "4min", "5s")


@pytest.mark.wall_clock
async def test_an_alter_behind_a_held_lock_fails_fast() -> None:
    table = f"migration_probe_{uuid4().hex[:12]}"
    holder_engine, migrating = _engine(), _engine()
    bound_migration_waits(migrating.sync_engine, lock_timeout="200ms", statement_timeout="1min")
    try:
        async with holder_engine.begin() as setup:
            await setup.execute(text(f"CREATE TABLE {table} (id int)"))
        async with holder_engine.connect() as holder:
            await holder.begin()
            await holder.execute(text(f"LOCK TABLE {table} IN ACCESS SHARE MODE"))  # held
            started = time.monotonic()
            with pytest.raises(DBAPIError, match="lock timeout"):
                async with migrating.begin() as conn:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN extra text"))
            waited = time.monotonic() - started
            await holder.rollback()
        assert waited < 5, f"waited {waited:.1f}s for the lock"
    finally:
        async with holder_engine.begin() as cleanup:
            await cleanup.execute(text(f"DROP TABLE IF EXISTS {table}"))
        await asyncio.gather(holder_engine.dispose(), migrating.dispose())


@pytest.mark.parametrize("bad", ["5 seconds; DROP TABLE users", "", "five"])
def test_a_malformed_duration_is_refused(bad: str) -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="Postgres duration"):
        bound_migration_waits(engine.sync_engine, lock_timeout=bad, statement_timeout="1min")


def test_other_databases_are_left_alone() -> None:
    engine = create_engine("sqlite://")
    bound_migration_waits(engine, lock_timeout="5s", statement_timeout="1min")
    with engine.connect() as conn, conn.begin():
        assert conn.execute(text("SELECT 1")).scalar() == 1
