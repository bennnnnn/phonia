"""Retain per-user search reservations across search deletion and recreation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0101_job_manual_allowance"
down_revision = "0100_job_search_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_manual_allowances",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("local_day", sa.String(10), primary_key=True),
        sa.Column("reserved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("""INSERT INTO job_manual_allowances (user_id,local_day,reserved_count,last_requested_at)
        SELECT p.user_id,r.local_day,count(*)::integer,max(r.created_at)
        FROM job_search_runs r JOIN job_search_profiles p ON p.id=r.profile_id
        WHERE r.manual GROUP BY p.user_id,r.local_day""")


def downgrade() -> None:
    op.drop_table("job_manual_allowances")
