"""Group memory facts into documents: a topic per fact, area titles, history scan.

Revision ID: 0097_memory_documents
Revises: 0096_push_android_channels

Facts stay atomic rows. `memories.topic` names the document a fact belongs to
(profile, preferences, tech-stack, ... or `area:<slug>` for one project or part
of the user's life); `memory_areas` holds each area's title and one-line
summary. Existing rows get the topic for their type. `users.memory_history_
scanned_at` records the one pass memory makes over a user's recent chats.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0097_memory_documents"
down_revision: Union[str, None] = "0096_push_android_channels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("topic", sa.String(length=45), nullable=False, server_default="notes"),
    )
    op.execute(
        sa.text(
            "UPDATE memories SET topic = CASE type "
            "WHEN 'profile' THEN 'profile' "
            "WHEN 'preference' THEN 'preferences' "
            "WHEN 'project' THEN 'side-projects' "
            "WHEN 'focus' THEN 'recent-work' "
            "ELSE 'notes' END"
        )
    )
    op.create_index("ix_memories_user_topic_status", "memories", ["user_id", "topic", "status"])
    op.create_table(
        "memory_areas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=45), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.String(length=240), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_memory_areas_user_key"),
    )
    op.add_column(
        "users",
        sa.Column("memory_history_scanned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "memory_history_scanned_at")
    op.drop_table("memory_areas")
    op.drop_index("ix_memories_user_topic_status", table_name="memories")
    op.drop_column("memories", "topic")
