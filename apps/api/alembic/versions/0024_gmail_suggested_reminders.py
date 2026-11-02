"""Gmail connections and suggested reminders

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_gmail_connections",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("google_email", sa.String(length=320), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(length=512), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "suggested_reminders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("source_snippet", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("todo_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["todo_id"], ["todo_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "gmail_message_id", name="uq_suggested_reminders_user_message"
        ),
    )
    op.create_index(
        "ix_suggested_reminders_user_status",
        "suggested_reminders",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_suggested_reminders_user_due",
        "suggested_reminders",
        ["user_id", "due_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_suggested_reminders_user_due", table_name="suggested_reminders")
    op.drop_index("ix_suggested_reminders_user_status", table_name="suggested_reminders")
    op.drop_table("suggested_reminders")
    op.drop_table("user_gmail_connections")
