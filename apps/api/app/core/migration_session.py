"""Bounded waits for schema migrations (``alembic/env.py``).

``ALTER TABLE`` takes an ACCESS EXCLUSIVE lock. Waiting for it behind a long
query (an account delete is one cascading ``DELETE``) queues every later query
on that table behind the migration: on ``users`` that is every request. With a
``lock_timeout`` the migration fails fast instead and the release command
stops the deploy; the old release keeps serving. ``statement_timeout`` bounds
how long one statement may hold what it took.

Both are set with ``set_config(..., is_local => true)`` (``SET LOCAL``) at the
start of every transaction, so they end with it: safe through a transaction-
mode pooler (PgBouncer, Neon's ``-pooler`` host), where a session ``SET`` would
leak to whichever client gets the server connection next. A migration that
runs outside a transaction (``autocommit_block`` for ``CREATE INDEX
CONCURRENTLY``) is not bounded by them, which is what such a migration needs.
"""

import re

from sqlalchemy import Connection, Engine, event, text

# Postgres duration: a number with an optional unit (5s, 300ms, 4min, 1h; 0 = off).
_DURATION = re.compile(r"^\d+\s*(us|ms|s|min|h|d)?$")


def _checked(name: str, value: str) -> str:
    if not _DURATION.match(value.strip()):
        raise ValueError(f"{name} must be a Postgres duration like '5s' or '4min', got {value!r}")
    return value.strip()


def bound_migration_waits(engine: Engine, *, lock_timeout: str, statement_timeout: str) -> None:
    """Start every transaction on ``engine`` with these local timeouts (Postgres only)."""
    if engine.dialect.name != "postgresql":
        return
    settings = {
        "lock_timeout": _checked("lock_timeout", lock_timeout),
        "statement_timeout": _checked("statement_timeout", statement_timeout),
    }

    def _on_begin(connection: Connection) -> None:
        for name, value in settings.items():
            connection.execute(
                text("SELECT set_config(:name, :value, true)"), {"name": name, "value": value}
            )

    event.listen(engine, "begin", _on_begin)
