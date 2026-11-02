"""Drop the chat archive: ``chats.archived`` and its index.

Revision ID: 0123_drop_chat_archive
Revises: 0122_todo_due_set_at

Archiving chats is removed from the product: no route, drawer section or settings page
reads or writes ``chats.archived`` any more, so the flag and ``ix_chats_user_archived``
(``user_id, archived``, migration 0029) go. Every chat is now listed in the drawer.
The downgrade restores the column (every chat unarchived) and its index.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0123_drop_chat_archive"
down_revision: Union[str, None] = "0122_todo_due_set_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # expand-contract: this app has never been deployed, so no running or rollback-candidate
    # image reads chats.archived; the release that removes the chat archive stops reading it.
    op.drop_index("ix_chats_user_archived", table_name="chats")
    op.drop_column("chats", "archived")


def downgrade() -> None:
    op.add_column(
        "chats",
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_chats_user_archived", "chats", ["user_id", "archived"])
