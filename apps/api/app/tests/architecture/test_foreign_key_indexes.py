"""Every foreign key has an index led by its column.

A delete on the referenced table looks up the referencing rows once per deleted row,
for ``CASCADE`` and ``SET NULL`` alike. With no index led by the column each lookup is
a full scan: an account delete scanned ``memories`` once per message and per fact, and
long-chat and account deletes would have run past the 120 s statement timeout (0116).
The ORM is checked here; ``test_schema_matches_migrations`` holds the database to it.
"""

from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Table

import app.models.orm  # noqa: F401  (registers every table, as alembic's env.py does)
from app.core.db import Base


def _leading_columns(table: Table) -> set[str]:
    """The first column of every index, unique constraint and the primary key."""
    leading = {index.columns.values()[0].name for index in table.indexes if index.columns}
    for constraint in table.constraints:
        columns = list(getattr(constraint, "columns", ()))
        if columns and not isinstance(constraint, ForeignKeyConstraint):
            leading.add(columns[0].name)
    return leading


def test_every_foreign_key_column_leads_an_index() -> None:
    unindexed = []
    for table in Base.metadata.tables.values():
        leading = _leading_columns(table)
        for constraint in table.foreign_key_constraints:
            first = constraint.column_keys[0]
            if first not in leading:
                unindexed.append(f"{table.name}.{first} -> {constraint.referred_table.name}")
    assert len(Base.metadata.tables) > 10, "every model should be registered"
    assert not unindexed, "foreign keys with no index led by their column:\n" + "\n".join(
        sorted(unindexed)
    )
