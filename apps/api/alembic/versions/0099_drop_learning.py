"""Drop the language-learning product schema.

Revision ID: 0099_drop_learning
Revises: 0098_memory_edited_at

Removes vocabulary catalogs, learning classes, practice history, and the
chat/todo columns that existed only to point at those classes. Chat, memory,
and reminder data stay.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0099_drop_learning"
down_revision: Union[str, None] = "0098_memory_edited_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_chats_user_project", table_name="chats")
    op.drop_constraint("fk_chats_project_id", "chats", type_="foreignkey")
    op.drop_column("chats", "project_id")
    op.drop_constraint("ck_chats_quiz_mode", "chats", type_="check")
    op.drop_column("chats", "quiz_mode")

    op.drop_index("ix_todo_items_user_project", table_name="todo_items")
    op.drop_constraint("fk_todo_items_project_id", "todo_items", type_="foreignkey")
    op.drop_column("todo_items", "project_id")

    op.drop_table("learning_practice_events")
    op.drop_table("quiz_miss_events")
    op.drop_table("project_items")
    op.drop_table("projects")
    op.drop_table("vocab_entries")
    op.drop_table("vocab_decks")


def downgrade() -> None:
    op.create_table(
        "vocab_decks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_language", sa.String(length=10), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="chapter"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("target_language", "slug", name="uq_vocab_decks_lang_slug"),
        sa.CheckConstraint("kind IN ('chapter', 'sat')", name="ck_vocab_decks_kind"),
    )
    op.create_index(
        "ix_vocab_decks_language_sort", "vocab_decks", ["target_language", "sort_order"]
    )
    op.create_table(
        "vocab_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("deck_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("example_sentence", sa.Text(), nullable=True),
        sa.Column("ipa", sa.String(length=80), nullable=True),
        sa.Column("part_of_speech", sa.String(length=30), nullable=True),
        sa.Column("vocabulary_kind", sa.String(length=30), nullable=False, server_default="word"),
        sa.Column("verb_kind", sa.String(length=30), nullable=True),
        sa.Column("noun_kind", sa.String(length=30), nullable=True),
        sa.Column("simple_gloss", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["deck_id"], ["vocab_decks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("deck_id", "content", name="uq_vocab_entries_deck_content"),
    )
    op.create_index("ix_vocab_entries_deck_sort", "vocab_entries", ["deck_id", "sort_order"])
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=50), nullable=True, server_default="language"),
        sa.Column("target_language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("native_language", sa.String(length=10), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=False, server_default="level1"),
        sa.Column("daily_goal", sa.Integer(), nullable=True),
        sa.Column("daily_goal_history", postgresql.JSONB(), nullable=True),
        sa.Column("learning_path", postgresql.JSONB(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("kind IN ('language')", name="ck_projects_kind"),
        sa.CheckConstraint(
            "level IN ('level1', 'level2', 'level3', 'level4', 'level5', 'level6')",
            name="ck_projects_level",
        ),
    )
    op.create_index("ix_projects_user_updated", "projects", ["user_id", "updated_at"])
    op.create_index("ix_projects_user_kind", "projects", ["user_id", "kind"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_projects_user_language_target_active
        ON projects (user_id, target_language)
        WHERE kind = 'language' AND archived = false
        """
    )
    op.create_table(
        "project_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("list_title", sa.String(length=200), nullable=False, server_default="General"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("example_sentence", sa.Text(), nullable=True),
        sa.Column("ipa", sa.String(length=80), nullable=True),
        sa.Column("part_of_speech", sa.String(length=30), nullable=True),
        sa.Column("vocabulary_kind", sa.String(length=30), nullable=False, server_default="word"),
        sa.Column("verb_kind", sa.String(length=30), nullable=True),
        sa.Column("noun_kind", sa.String(length=30), nullable=True),
        sa.Column("simple_gloss", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("mastered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mastered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_incorrect_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quiz_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quiz_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pronunciation_url", sa.String(length=500), nullable=True),
        sa.Column("catalog_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["catalog_entry_id"], ["vocab_entries.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "project_id", "list_title", "content", name="uq_project_items_project_list_content"
        ),
        sa.CheckConstraint(
            "status IN ('new', 'learning', 'mastered')", name="ck_project_items_status"
        ),
    )
    op.create_index("ix_project_items_project_list", "project_items", ["project_id", "list_title"])
    op.create_index("ix_project_items_user_project", "project_items", ["user_id", "project_id"])
    op.create_index(
        "ix_project_items_status_review",
        "project_items",
        ["project_id", "status", "last_reviewed_at"],
    )
    op.create_index("ix_project_items_project_due_at", "project_items", ["project_id", "due_at"])
    op.create_table(
        "quiz_miss_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["project_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_quiz_miss_events_item_occurred", "quiz_miss_events", ["item_id", "occurred_at"]
    )
    op.create_index("ix_quiz_miss_events_user", "quiz_miss_events", ["user_id"])
    op.create_table(
        "learning_practice_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("was_correct", sa.Boolean(), nullable=False),
        sa.Column("completes_word", sa.Boolean(), nullable=False),
        sa.Column("newly_mastered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["project_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "attempt_id", name="uq_learning_practice_user_attempt"),
        sa.CheckConstraint(
            "NOT completes_word OR was_correct", name="ck_learning_practice_completion"
        ),
        sa.CheckConstraint(
            "NOT newly_mastered OR completes_word", name="ck_learning_practice_new_mastery"
        ),
    )
    op.create_index(
        "ix_learning_practice_user_time",
        "learning_practice_events",
        ["user_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_learning_practice_project_time",
        "learning_practice_events",
        ["project_id", "occurred_at"],
    )
    op.create_index(
        "ix_learning_practice_item_time", "learning_practice_events", ["item_id", "occurred_at"]
    )

    op.add_column("chats", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_chats_project_id", "chats", "projects", ["project_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_chats_user_project", "chats", ["user_id", "project_id"])
    op.add_column("chats", sa.Column("quiz_mode", sa.String(length=16), nullable=True))
    op.create_check_constraint(
        "ck_chats_quiz_mode",
        "chats",
        "quiz_mode IS NULL OR quiz_mode IN ('exam', 'chat')",
    )
    op.add_column(
        "todo_items", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_todo_items_project_id",
        "todo_items",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_todo_items_user_project", "todo_items", ["user_id", "project_id"])
