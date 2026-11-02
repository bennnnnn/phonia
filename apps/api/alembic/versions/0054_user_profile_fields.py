"""Add structured profile fields: age, country, job

Revision ID: 0054_user_profile_fields
Revises: 0053_check_constraints_enums
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054_user_profile_fields"
down_revision: Union[str, None] = "0053_check_constraints_enums"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("age", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("job", sa.String(length=128), nullable=True))
    op.create_check_constraint(
        "ck_users_age_range",
        "users",
        "age IS NULL OR (age >= 13 AND age <= 120)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_age_range", "users", type_="check")
    op.drop_column("users", "job")
    op.drop_column("users", "country")
    op.drop_column("users", "age")
