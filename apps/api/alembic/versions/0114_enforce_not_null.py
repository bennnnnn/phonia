"""Enforce NOT NULL on columns the ORM already treats as required.

Revision ID: 0114_enforce_not_null
Revises: 0113_product_event_names

Every column here has a server default and the code never writes NULL to it,
but the early migrations left it nullable, so ``alembic check`` reported drift.
Each column is backfilled from its default, then a NOT VALID check is added and
validated (no long ACCESS EXCLUSIVE lock), so SET NOT NULL skips the table scan.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0114_enforce_not_null"
down_revision: Union[str, None] = "0113_product_event_names"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, value for a NULL left by an early row)
_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("attachment_chunks", "created_at", "now()"),
    ("chats", "model", "'free-chat'"),
    ("chats", "created_at", "now()"),
    ("chats", "updated_at", "now()"),
    ("memories", "created_at", "now()"),
    ("memories", "updated_at", "now()"),
    ("message_chunks", "created_at", "now()"),
    ("messages", "input_tokens", "0"),
    ("messages", "output_tokens", "0"),
    ("messages", "created_at", "now()"),
    ("usage_daily", "input_tokens", "0"),
    ("usage_daily", "output_tokens", "0"),
    ("users", "default_model", "'free-chat'"),
    ("users", "response_style", "'balanced'"),
    ("users", "memory_enabled", "true"),
    ("users", "created_at", "now()"),
    ("users", "updated_at", "now()"),
)


def upgrade() -> None:
    for table, column, fill in _COLUMNS:
        check = f"ck_{table}_{column}_not_null"
        op.execute(f"UPDATE {table} SET {column} = {fill} WHERE {column} IS NULL")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {check} CHECK ({column} IS NOT NULL) NOT VALID"
        )
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {check}")
        op.alter_column(table, column, nullable=False)
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {check}")


def downgrade() -> None:
    for table, column, _fill in reversed(_COLUMNS):
        op.alter_column(table, column, nullable=True)
