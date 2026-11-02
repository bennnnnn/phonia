"""Hide send-clones from Library (reuse an existing file in a new chat).

Revision ID: 0078_attach_lib_visible
Revises: 0077_vocab_word_gloss
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0078_attach_lib_visible"
down_revision: Union[str, None] = "0077_vocab_word_gloss"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column(
            "library_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("attachments", "library_visible")
