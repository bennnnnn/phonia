"""Record when an attachment was first linked, and index the attachment lookups.

Revision ID: 0115_attachment_linked_at
Revises: 0114_enforce_not_null

An upload confirmed but never sent kept ``message_id`` NULL forever, exactly like a
Library item whose chat was deleted, so the orphan reaper could not tell them
apart and kept both. ``linked_at`` is set the first time a message links the row.
Existing rows cannot say whether they were ever linked, so every linked or
verified row is backfilled as linked: only uploads from now on can be reaped as
never sent. Adding a nullable column is an expand; the old release ignores it.

The indexes serve a message delete (FK SET NULL on ``message_id``), a chat delete
(FK CASCADE on ``attachment_chunks.chat_id``) and the reaper's scan of unlinked
rows by age. They are built CONCURRENTLY so writes keep flowing during the build.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0115_attachment_linked_at"
down_revision: Union[str, None] = "0114_enforce_not_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("attachments", sa.Column("linked_at", sa.DateTime(timezone=True)))
    op.execute(
        "UPDATE attachments SET linked_at = created_at "
        "WHERE message_id IS NOT NULL OR verified_at IS NOT NULL"
    )
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_attachments_message",
            "attachments",
            ["message_id"],
            postgresql_where=sa.text("message_id IS NOT NULL"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "ix_attachments_unlinked_created",
            "attachments",
            ["created_at"],
            postgresql_where=sa.text("message_id IS NULL"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "ix_attachment_chunks_chat",
            "attachment_chunks",
            ["chat_id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_attachment_chunks_chat",
            table_name="attachment_chunks",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_attachments_unlinked_created",
            table_name="attachments",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_attachments_message",
            table_name="attachments",
            postgresql_concurrently=True,
            if_exists=True,
        )
    op.drop_column("attachments", "linked_at")
