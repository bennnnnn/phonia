"""Retire My Job résumé storage and invalidate résumé-based assessments."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0103_remove_job_resume"
down_revision = "0102_job_applied_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "UPDATE job_search_profiles SET revision = revision + 1 "
        "WHERE resume_attachment_id IS NOT NULL OR resume_filename IS NOT NULL "
        "OR resume_text IS NOT NULL OR resume_profile IS NOT NULL"
    )
    for column in ("resume_attachment_id", "resume_filename", "resume_text", "resume_profile"):
        op.drop_column("job_search_profiles", column)


def downgrade() -> None:
    # Restores the schema; retired résumé data is recovered from a database snapshot.
    op.add_column(
        "job_search_profiles", sa.Column("resume_attachment_id", postgresql.UUID(as_uuid=True))
    )
    op.add_column("job_search_profiles", sa.Column("resume_filename", sa.String(255)))
    op.add_column("job_search_profiles", sa.Column("resume_text", sa.Text()))
    op.add_column("job_search_profiles", sa.Column("resume_profile", sa.JSON()))
    op.create_foreign_key(
        "job_search_profiles_resume_attachment_id_fkey",
        "job_search_profiles",
        "attachments",
        ["resume_attachment_id"],
        ["id"],
        ondelete="SET NULL",
    )
