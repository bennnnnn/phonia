"""Add 'search' to attachments.source (reference-photo lookup)

Revision ID: 0082_attachment_source_search
Revises: 0081_todo_source

Distinguishes web-image-search lookups (real reference photos mirrored from
a search provider) from AI-generated images and user uploads, so the orphan
reaper and gallery filters can treat them distinctly from 'generated'.

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)`` (see 0063).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0082_attachment_source_search"
down_revision: Union[str, None] = "0081_todo_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_attachments_source", "attachments", type_="check")
    op.create_check_constraint(
        "ck_attachments_source",
        "attachments",
        "source IN ('upload', 'generated', 'search')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_attachments_source", "attachments", type_="check")
    op.create_check_constraint(
        "ck_attachments_source",
        "attachments",
        "source IN ('upload', 'generated')",
    )
