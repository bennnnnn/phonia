from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core import pool_liveness
from app.core.config import get_settings
from app.core.database_url import (
    engine_connect_args,
    pool_recycle_seconds_for_url,
    prepare_asyncpg_url,
)


class Base(DeclarativeBase):
    pass


settings = get_settings()
_db_url, _url_connect_args = prepare_asyncpg_url(
    settings.database_url,
    prefer_neon_pooler=settings.database_prefer_neon_pooler,
)
_connect_args = engine_connect_args(settings, _url_connect_args)
engine = create_async_engine(
    _db_url,
    echo=False,
    connect_args=_connect_args,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    # Fail fast under burst instead of the 30s default — a stalled checkout
    # should surface as a fast error/retry, not a 30s TTFT hang.
    pool_timeout=settings.db_pool_timeout_seconds,
    pool_recycle=pool_recycle_seconds_for_url(_db_url),
    # The connection returned last goes out first: busy ones stay warm and spare
    # ones age into the idle ping or the recycle (core/pool_liveness.py).
    pool_use_lifo=True,
    # A failed statement's error otherwise quotes its parameters: a message's or a
    # memory's text in the log line and the Sentry event.
    hide_parameters=True,
)
# Instead of pool_pre_ping's three round trips on every checkout.
pool_liveness.install(engine.sync_engine, idle_ping_seconds=settings.db_idle_ping_seconds)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def warmup_db_pool() -> None:
    """Open one connection at startup so the first chat turn skips cold connect."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
