"""Replace generic automations with dedicated My Job tables.

Revision ID: 0090_job_search
Revises: 0089_automations
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0090_job_search"
down_revision: Union[str, None] = "0089_automations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The generic unattended-prompt product is intentionally retired rather
    # than hidden behind a new kind/config blob. Delete its private chat rows
    # first so they cannot reappear in the normal chat drawer after the table
    # that marked them as hidden is removed.
    op.execute(sa.text("DELETE FROM chats WHERE id IN (SELECT chat_id FROM automations)"))
    op.drop_table("automations")

    op.create_table(
        "job_search_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_roles", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("work_modes", sa.JSON(), nullable=False),
        sa.Column("experience_levels", sa.JSON(), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("requires_sponsorship", sa.Boolean(), nullable=True),
        sa.Column("excluded_companies", sa.JSON(), nullable=False),
        sa.Column("background", sa.Text(), nullable=True),
        sa.Column("resume_attachment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resume_filename", sa.String(length=255), nullable=True),
        sa.Column("resume_text", sa.Text(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("frequency", sa.String(length=16), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=24), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "result_count IN (5, 10, 15)",
            name="ck_job_search_profiles_result_count",
        ),
        sa.CheckConstraint(
            "frequency IN ('daily', 'weekdays', 'weekly', 'monthly')",
            name="ck_job_search_profiles_frequency",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused')",
            name="ck_job_search_profiles_status",
        ),
        sa.CheckConstraint(
            "last_run_status IS NULL OR last_run_status IN ('ok', 'error', 'skipped_quota')",
            name="ck_job_search_profiles_last_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["resume_attachment_id"],
            ["attachments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_job_search_profiles_user"),
    )
    op.create_index(
        "ix_job_search_profiles_due",
        "job_search_profiles",
        ["status", "next_run_at"],
        unique=False,
    )

    op.create_table(
        "job_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_url", sa.String(length=2000), nullable=False),
        sa.Column("canonical_url_hash", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("company", sa.String(length=180), nullable=False),
        sa.Column("location", sa.String(length=180), nullable=True),
        sa.Column("work_mode", sa.String(length=16), nullable=True),
        sa.Column("salary", sa.String(length=160), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("posted_at", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("match_reasons", sa.JSON(), nullable=False),
        sa.Column("gap", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("found_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "work_mode IS NULL OR work_mode IN ('remote', 'hybrid', 'onsite')",
            name="ck_job_matches_work_mode",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'saved', 'applied', 'hidden')",
            name="ck_job_matches_status",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["job_search_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id",
            "canonical_url_hash",
            name="uq_job_matches_profile_url_hash",
        ),
    )
    op.create_index(
        "ix_job_matches_profile_status_found",
        "job_matches",
        ["profile_id", "status", "found_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_matches_profile_status_found", table_name="job_matches")
    op.drop_table("job_matches")
    op.drop_index("ix_job_search_profiles_due", table_name="job_search_profiles")
    op.drop_table("job_search_profiles")

    # Recreate the historical primitive only for migration reversibility. No
    # application code depends on it after this revision.
    op.create_table(
        "automations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("frequency", sa.String(length=16), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "frequency IN ('once', 'daily', 'weekdays', 'weekly', 'monthly')",
            name="ck_automations_frequency",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed')",
            name="ck_automations_status",
        ),
        sa.CheckConstraint(
            "last_run_status IS NULL OR last_run_status IN ('ok', 'skipped_quota', 'error')",
            name="ck_automations_last_run_status",
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id"),
    )
    op.create_index("ix_automations_user_id", "automations", ["user_id"], unique=False)
    op.create_index(
        "ix_automations_status_next_run",
        "automations",
        ["status", "next_run_at"],
        unique=False,
    )
