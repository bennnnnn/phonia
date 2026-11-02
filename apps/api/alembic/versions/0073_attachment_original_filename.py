"""Add attachments.original_filename for gallery search.

Revision ID: 0073_attachment_filename
Revises: 0072_vocab_domain_tree

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)`` (see 0063).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0073_attachment_filename"
down_revision: Union[str, None] = "0072_vocab_domain_tree"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("original_filename", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attachments", "original_filename")
