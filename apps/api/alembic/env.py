import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.core.database_url import prepare_asyncpg_url
from app.core.db import Base
from app.core.migration_session import bound_migration_waits
from app.models.orm import Chat, Memory, Message, UsageDaily, User  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()
_db_url, _connect_args = prepare_asyncpg_url(settings.database_url)
config.set_main_option("sqlalchemy.url", _db_url)


# Schema objects a migration owns that the ORM deliberately leaves out, so that
# autogenerate (and ``alembic check``) does not propose dropping them.
_MIGRATION_ONLY_INDEXES = frozenset(
    {
        # Partial unique on (user_id, lower(content), due_at) for open dated to-dos
        # (0084). Not on TodoItem: SQLite ``__table__.create()`` fixtures can't build
        # the Postgres expression.
        "uq_todo_open_content_due",
    }
)


def include_object(obj, name, type_, reflected, compare_to) -> bool:  # type: ignore[no-untyped-def]
    return not (type_ == "index" and reflected and name in _MIGRATION_ONLY_INDEXES)


def _engine_config() -> dict:
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _db_url
    return section


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    # transaction_per_migration=True lets individual revisions opt into
    # ``with op.get_context().autocommit_block():`` for CREATE INDEX CONCURRENTLY
    # (which cannot run inside a transaction). Default migrations still wrap
    # each revision in its own transaction.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        _engine_config(),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=_connect_args,
    )
    # Fail fast instead of queueing every query on a table behind an ALTER
    # waiting for its lock (core/migration_session.py).
    bound_migration_waits(
        connectable.sync_engine,
        lock_timeout=settings.migration_lock_timeout,
        statement_timeout=settings.migration_statement_timeout,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
