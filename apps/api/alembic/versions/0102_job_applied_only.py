"""Remove application stages while retaining jobs and their application records."""

from alembic import op

revision = "0102_job_applied_only"
down_revision = "0101_job_manual_allowance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "UPDATE job_matches SET status = 'applied' "
        "WHERE status IN ('interviewing', 'offer', 'rejected')"
    )
    op.drop_constraint("ck_job_matches_status", "job_matches", type_="check")
    op.create_check_constraint(
        "ck_job_matches_status", "job_matches", "status IN ('new', 'saved', 'applied', 'hidden')"
    )


def downgrade() -> None:
    # Restores the old allowed values; converted rows remain Applied.
    op.drop_constraint("ck_job_matches_status", "job_matches", type_="check")
    op.create_check_constraint(
        "ck_job_matches_status",
        "job_matches",
        "status IN ('new', 'saved', 'applied', 'interviewing', 'offer', 'rejected', 'hidden')",
    )
