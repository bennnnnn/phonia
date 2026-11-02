"""Quiet hours columns on users.

Revision ID: 0088_user_quiet_hrs
Revises: 0087_memory_facts

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)`` (see 0063).

Idempotent: a local 0086_user_quiet_hrs (never on main) may already have
added these columns. Skip if they exist.
"""

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0088_user_quiet_hrs"
down_revision: Union[str, None] = "0087_memory_facts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS: tuple[tuple[str, sa.Column[Any]], ...] = (
    (
        "quiet_hours_enabled",
        sa.Column(
            "quiet_hours_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    ),
    (
        "quiet_hours_start_minute",
        sa.Column(
            "quiet_hours_start_minute",
            sa.Integer(),
            nullable=False,
            server_default="1320",
        ),
    ),
    (
        "quiet_hours_end_minute",
        sa.Column(
            "quiet_hours_end_minute",
            sa.Integer(),
            nullable=False,
            server_default="420",
        ),
    ),
)

_CHECKS = (
    (
        "ck_users_quiet_hours_start",
        "quiet_hours_start_minute >= 0 AND quiet_hours_start_minute <= 1439",
    ),
    (
        "ck_users_quiet_hours_end",
        "quiet_hours_end_minute >= 0 AND quiet_hours_end_minute <= 1439",
    ),
)


def _existing_columns() -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {col["name"] for col in insp.get_columns("users")}


def _existing_checks() -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_check_constraints("users") if c["name"]}


def upgrade() -> None:
    cols = _existing_columns()
    for name, column in _COLS:
        if name not in cols:
            op.add_column("users", column)
    checks = _existing_checks()
    for name, sql in _CHECKS:
        if name not in checks:
            op.create_check_constraint(name, "users", sql)


def downgrade() -> None:
    checks = _existing_checks()
    for name, _sql in reversed(_CHECKS):
        if name in checks:
            op.drop_constraint(name, "users", type_="check")
    cols = _existing_columns()
    for name, _column in reversed(_COLS):
        if name in cols:
            op.drop_column("users", name)
