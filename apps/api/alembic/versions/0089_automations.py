"""Automations table.

Revision ID: 0089_automations
Revises: 0088_user_quiet_hrs

New feature, separate from Schedule: a recurring prompt run unattended
through the chat turn engine, posting into its own dedicated `chat_id`
thread. See apps/api/app/models/orm/automations.py.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0089_automations"
down_revision: Union[str, None] = "0088_user_quiet_hrs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("frequency", sa.String(length=16), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", name="uq_automations_chat_id"),
        sa.CheckConstraint(
            "frequency IN ('once', 'daily', 'weekdays', 'weekly', 'monthly')",
            name="ck_automations_frequency",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed')",
            name="ck_automations_status",
        ),
        sa.CheckConstraint(
            "last_run_status IS NULL OR last_run_status IN ('ok', 'skipped_quota', 'error')",
            name="ck_automations_last_run_status",
        ),
    )
    op.create_index("ix_automations_user_id", "automations", ["user_id"])
    op.create_index("ix_automations_status_next_run", "automations", ["status", "next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_automations_status_next_run", table_name="automations")
    op.drop_index("ix_automations_user_id", table_name="automations")
    op.drop_table("automations")
