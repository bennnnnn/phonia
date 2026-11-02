"""Hide reference-photo lookup copies from Library.

Revision ID: 0083_search_lib_hidden
Revises: 0082_attachment_source_search

Lookup photos are chat-only. Setting ``library_visible`` false hides already-
saved ``source='search'`` rows from the gallery and lets the orphan reaper
drop them after the chat is deleted (unlike user uploads / generated images).

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)`` (see 0063).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0083_search_lib_hidden"
down_revision: Union[str, None] = "0082_attachment_source_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE attachments SET library_visible = false WHERE source = 'search'")


def downgrade() -> None:
    op.execute("UPDATE attachments SET library_visible = true WHERE source = 'search'")
