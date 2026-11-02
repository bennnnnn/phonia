"""Memory embeddings for semantic recall (JSON vectors)

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memories", sa.Column("embedding_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("memories", "embedding_json")
