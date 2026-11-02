"""Add attachments.source (upload vs generated)

Revision ID: 0059_attachment_source
Revises: 0058_drop_legacy_project_kinds

Distinguishes user uploads from image-generation outputs so orphan reaping
refunds the correct daily quota slot (imgup vs imggen).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0059_attachment_source"
down_revision: Union[str, None] = "0058_drop_legacy_project_kinds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("source", sa.String(length=16), server_default="upload", nullable=False),
    )
    op.create_check_constraint(
        "ck_attachments_source",
        "attachments",
        "source IN ('upload', 'generated')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_attachments_source", "attachments", type_="check")
    op.drop_column("attachments", "source")
