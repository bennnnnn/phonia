"""add apple_sub to users; google_sub nullable

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("apple_sub", sa.String(), nullable=True))
    op.create_unique_constraint("uq_users_apple_sub", "users", ["apple_sub"])
    op.alter_column("users", "google_sub", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    # Apple Sign-In was added as an alternative to Google Sign-In, so any
    # user who has ever signed in with Apple only (and never linked Google)
    # has google_sub IS NULL. Restoring google_sub to NOT NULL is only safe
    # if no such user exists. Check first and fail loudly with a clear
    # error rather than let the ALTER COLUMN error out unpredictably.
    conn = op.get_bind()
    apple_only_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE google_sub IS NULL")
    ).scalar_one()
    if apple_only_count:
        raise RuntimeError(
            "Cannot downgrade migration 0038: "
            f"{apple_only_count} user(s) have google_sub IS NULL "
            "(Apple-only sign-in). Restoring users.google_sub to NOT NULL "
            "would fail or corrupt data. Resolve those rows (backfill "
            "google_sub or remove the affected users) before downgrading "
            "past this revision."
        )
    op.alter_column("users", "google_sub", existing_type=sa.String(), nullable=False)
    op.drop_constraint("uq_users_apple_sub", "users", type_="unique")
    op.drop_column("users", "apple_sub")
