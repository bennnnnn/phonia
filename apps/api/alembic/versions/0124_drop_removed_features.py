"""Drop what the removed features stored: model choice, tone, location, suggestions, pictures.

Revision ID: 0124_drop_removed_features
Revises: 0123_drop_chat_archive

Phonia removed the model picker (``users.default_model``, ``users.enabled_models``,
``chats.model``), the reply tone setting (``users.response_tone`` and its check), device
location (``users.location``, ``users.location_enabled``), the retired proactive
suggestions (the ``suggestions`` table) and AI image generation (``attachments.source``
no longer takes ``'generated'``). Nothing reads any of them any more.

Memory's topics were cut down to a student's (tech-stack, side-projects and recent-work
are gone): a fact filed under one of them moves to notes or progress, and a lesson line
("Learning X: ...") moves from goals to progress, so no page is left without a title.

The downgrade restores every column with its old default (each user back on Auto with
the casual tone, no location; each chat on ``free-chat``), the check constraints and an
empty ``suggestions`` table. Moved memory facts and deleted generated pictures stay as
they are.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0124_drop_removed_features"
down_revision: Union[str, None] = "0123_drop_chat_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCES_BEFORE = "source IN ('upload', 'generated', 'search')"
_SOURCES_AFTER = "source IN ('upload', 'search')"
_TONES = "response_tone IN ('funny', 'professional', 'casual', 'soft')"


def upgrade() -> None:
    # expand-contract: this app has never been deployed, so no running or rollback-candidate
    # image reads these columns or the suggestions table; the release that removes the
    # model picker, tone, location, suggestions and image generation stops reading them.
    op.drop_constraint("ck_users_response_tone", "users", type_="check")
    op.drop_column("users", "response_tone")
    op.drop_column("users", "default_model")
    op.drop_column("users", "enabled_models")
    op.drop_column("users", "location")
    op.drop_column("users", "location_enabled")
    op.drop_column("chats", "model")

    op.drop_index("ix_suggestions_user_id", table_name="suggestions")
    op.drop_table("suggestions")

    # No production data exists; a development database's generated pictures go with the
    # feature (their stored files are left to the orphan reaper).
    op.execute("DELETE FROM attachments WHERE source = 'generated'")
    op.drop_constraint("ck_attachments_source", "attachments", type_="check")
    op.create_check_constraint("ck_attachments_source", "attachments", _SOURCES_AFTER)

    op.execute(
        """
        UPDATE memories SET topic = CASE topic
            WHEN 'tech-stack' THEN 'notes'
            WHEN 'side-projects' THEN 'notes'
            WHEN 'recent-work' THEN 'progress'
            ELSE topic END
        WHERE topic IN ('tech-stack', 'side-projects', 'recent-work')
        """
    )
    op.execute(
        "UPDATE memories SET topic = 'progress' WHERE topic = 'goals' AND text LIKE 'Learning %:%'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_attachments_source", "attachments", type_="check")
    op.create_check_constraint("ck_attachments_source", "attachments", _SOURCES_BEFORE)

    op.create_table(
        "suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), server_default="general", nullable=False),
        sa.Column("source", sa.String(50), server_default="model", nullable=False),
        sa.Column("dismissed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_suggestions_user_id", "suggestions", ["user_id"])

    op.add_column(
        "chats", sa.Column("model", sa.String(), server_default="free-chat", nullable=False)
    )
    op.add_column(
        "users",
        sa.Column(
            "location_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column("users", sa.Column("location", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("enabled_models", postgresql.JSONB(), nullable=True))
    op.add_column(
        "users", sa.Column("default_model", sa.String(), server_default="free-chat", nullable=False)
    )
    op.add_column(
        "users", sa.Column("response_tone", sa.String(), server_default="casual", nullable=False)
    )
    op.create_check_constraint("ck_users_response_tone", "users", _TONES)
