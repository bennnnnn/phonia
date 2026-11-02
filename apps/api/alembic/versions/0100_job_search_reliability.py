"""Durable premium My Job runs, structured preferences, verified assessments and outbox.

Revision ID: 0100_job_search_reliability
Revises: 0099_drop_learning
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0100_job_search_reliability"
down_revision = "0099_drop_learning"
branch_labels = None
depends_on = None

_PROFILE = [
    sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("search_cursor", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("included_locations", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("excluded_locations", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("country", sa.String(100)),
    sa.Column("salary_currency", sa.String(3)),
    sa.Column("salary_period", sa.String(16), nullable=False, server_default="year"),
    sa.Column("years_experience", sa.Float()),
    sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("suspension_reason", sa.String(80)),
]
_MATCH = [
    sa.Column("assessment_revision", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("assessment", sa.JSON()),
    sa.Column("posting_identity", sa.String(500)),
    sa.Column("match_kind", sa.String(16), nullable=False, server_default="possible"),
    sa.Column("checked_at", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    for column in _PROFILE:
        op.add_column("job_search_profiles", column)
    for column in _MATCH:
        op.add_column("job_matches", column)
    # No guessed salary currency. Known legacy locations are backfilled below;
    # ambiguous geography and any legacy salary require explicit user review.
    profiles = sa.table(
        "job_search_profiles",
        sa.column("id", UUID()),
        sa.column("location", sa.String()),
        sa.column("salary_min", sa.Integer()),
        sa.column("included_locations", sa.JSON()),
        sa.column("country", sa.String()),
        sa.column("needs_review", sa.Boolean()),
    )
    known = {
        "california": {"country": "United States", "region": "California"},
        "dc": {"country": "United States", "region": "District of Columbia"},
        "united states": {"country": "United States"},
        "us": {"country": "United States"},
        "usa": {"country": "United States"},
        "canada": {"country": "Canada"},
        "germany": {"country": "Germany"},
        "united kingdom": {"country": "United Kingdom"},
        "australia": {"country": "Australia"},
        "india": {"country": "India"},
    }
    bind = op.get_bind()
    for row in bind.execute(sa.select(profiles.c.id, profiles.c.location, profiles.c.salary_min)):
        place = known.get((row.location or "").strip().casefold())
        bind.execute(
            profiles.update()
            .where(profiles.c.id == row.id)
            .values(
                included_locations=[place] if place else [],
                country=place["country"] if place else None,
                needs_review=bool((row.location and not place) or row.salary_min is not None),
            )
        )
    # Legacy free searches cannot start automatically after a later renewal.
    op.execute("""UPDATE job_search_profiles p
        SET status='paused', suspension_reason='pro_expired', revision=p.revision+1
        FROM users u WHERE u.id=p.user_id AND u.plan<>'pro' AND p.status='active'""")
    # The ORM definitions are frozen here through explicit table creation below.
    op.create_table(
        "job_search_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(),
            sa.ForeignKey("job_search_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_key", sa.String(160), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("manual", sa.Boolean(), nullable=False),
        sa.Column("local_day", sa.String(10), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("overrides", sa.JSON(), nullable=False),
        sa.Column("result_limit", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("qualifying_count", sa.Integer(), nullable=False),
        sa.Column("possible_count", sa.Integer(), nullable=False),
        sa.Column("new_match_count", sa.Integer(), nullable=False),
        sa.Column("match_ids", sa.JSON(), nullable=False),
        sa.Column("partial", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(240)),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.UniqueConstraint("profile_id", "request_key", name="uq_job_run_request"),
        sa.CheckConstraint(
            "state IN ('queued','running','completed','failed','limited','cancelled')",
            name="ck_job_run_state",
        ),
    )
    op.create_index("ix_job_run_profile_created", "job_search_runs", ["profile_id", "created_at"])
    op.create_index("ix_job_run_recovery", "job_search_runs", ["state", "lease_until"])
    op.create_table(
        "job_notification_events",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "run_id",
            UUID(),
            sa.ForeignKey("job_search_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("new_match_count", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("devices", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", name="uq_job_notification_run"),
    )


def downgrade() -> None:
    op.drop_table("job_notification_events")
    op.drop_table("job_search_runs")
    for column in reversed(_MATCH):
        op.drop_column("job_matches", column.name)
    for column in reversed(_PROFILE):
        op.drop_column("job_search_profiles", column.name)
