"""Store attachment index extract coverage for honest RAG prefixes.

Revision ID: 0085_attach_idx_cov
Revises: 0084_todo_open_due_uq

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)`` (see 0063).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0085_attach_idx_cov"
down_revision: Union[str, None] = "0084_todo_open_due_uq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("index_coverage_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attachments", "index_coverage_json")
