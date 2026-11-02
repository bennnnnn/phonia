"""Postgres connects and statements are bounded.

asyncpg's connect timeout defaulted to 60s and statements had no timeout at
all. The idle-connection ping (``core/pool_liveness``) runs a statement on
checkout, so one half-open
pooled connection (Neon restart, network blip) hung a request forever, and
``pool_timeout`` (5s) only covers waiting for a free slot.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings, get_settings
from app.core.database_url import engine_connect_args, prepare_asyncpg_url


@pytest.mark.parametrize(
    "overrides, base, expected",
    [
        ({}, {}, {"timeout": 10.0, "command_timeout": 120.0}),
        (
            {"db_connect_timeout_seconds": 3.0, "db_command_timeout_seconds": 30.0},
            {"ssl": "require"},
            {"ssl": "require", "timeout": 3.0, "command_timeout": 30.0},
        ),
        (
            {"db_connect_timeout_seconds": 0, "db_command_timeout_seconds": 0},
            {"ssl": "require"},
            {"ssl": "require"},
        ),
    ],
)
def test_engine_connect_args_bound_connect_and_statements(
    overrides: dict[str, float], base: dict[str, str], expected: dict[str, object]
) -> None:
    settings = Settings().model_copy(update=overrides)
    assert engine_connect_args(settings, base) == expected


def test_app_engine_uses_the_bounded_connect_args() -> None:
    from app.core import db

    assert db._connect_args.get("command_timeout") == get_settings().db_command_timeout_seconds
    assert db._connect_args.get("timeout") == get_settings().db_connect_timeout_seconds


@pytest.mark.wall_clock
async def test_command_timeout_cancels_a_slow_statement() -> None:
    url, base = prepare_asyncpg_url(get_settings().database_url)
    settings = Settings(db_connect_timeout_seconds=5.0, db_command_timeout_seconds=0.5)
    engine = create_async_engine(url, connect_args=engine_connect_args(settings, base))
    try:
        async with engine.connect() as conn:
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                await conn.execute(text("SELECT pg_sleep(5)"))
            assert time.monotonic() - started < 3
    except OSError as exc:  # pragma: no cover - no local Postgres
        pytest.skip(f"Postgres unavailable: {exc}")
    finally:
        await engine.dispose()
