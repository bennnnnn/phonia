"""Add the Plus plan.

Revision ID: 0107_plus_plan
Revises: 0106_drop_google_integrations

Plans are now free, plus (the lower paid plan) and pro (the top plan).
Existing ``pro`` rows are untouched: the single paid plan becomes the top plan
and keeps everything it had. No row changes, only the allowed values.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0107_plus_plan"
down_revision: Union[str, None] = "0106_drop_google_integrations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_plan")
    op.create_check_constraint("ck_users_plan", "users", "plan IN ('free', 'plus', 'pro')")


def downgrade() -> None:
    # Plus has no place in the two-plan schema; it keeps its paid models as free.
    op.execute("UPDATE users SET plan = 'free' WHERE plan = 'plus'")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_plan")
    op.create_check_constraint("ck_users_plan", "users", "plan IN ('free', 'pro')")
