"""Drop orphaned templates table

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-02

The Templates feature was removed (no router, no ORM model, no service, no
mobile UI). The `templates` table created in 0010 — and its built-in-title
unique index added in 0036 — are now dead schema. Drop them so production
doesn't carry an orphaned table with no code path. The `suggestions` table
created alongside it is unaffected (still in active use).
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ux_templates_builtin_title", table_name="templates")
    op.drop_index("ix_templates_user_id", table_name="templates")
    op.drop_table("templates")


def downgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="general"),
        sa.Column("is_builtin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_templates_user_id", "templates", ["user_id"])
    op.create_index(
        "ux_templates_builtin_title",
        "templates",
        ["title"],
        unique=True,
        postgresql_where="is_builtin = true",
    )
