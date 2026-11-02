"""Add CHECK constraints for enum-like columns beyond messages

Revision ID: 0053_check_constraints_enums
Revises: 0052_user_owned_cascades
Create Date: 2026-07-11

Several other columns are enum-like in practice (validated only by app/Pydantic
code) but are plain TEXT/VARCHAR at the DB level, same risk 0035 fixed for
messages.role/messages.feedback: a raw SQL fix-up, a bad migration, or an admin
script could write a value the read side then breaks on quietly.

Column value sets were confirmed against the current code (not FEATURES.md,
which is stale in places):

- memories.type: app/services/memory.py TYPE_PRIORITY / SECTION_LABELS and
  app/models/schemas.py MemoryType.
- projects.kind: app/services/projects.py LEARNING_PRODUCT_KINDS
  (language/trivia; "vocabulary" is a write alias normalised to "language"
  before insert — see normalize_project_kind / repositories/projects.create).
  "general" is kept as a valid value too: it is the column's own
  server_default from 0015, and FEATURES.md documents legacy kinds
  (programming, math, ...) as hidden-not-deleted, so we normalise strays to
  "general" below rather than excluding the column's own default value.
- projects.level: app/models/schemas.py LanguageLevel (level1..level6).
- users.plan: app/services/subscription.py / app/routers/webhooks.py only
  ever write "free" or "pro".
- users.response_tone: app/services/response_tone.py TONE_IDS.
- chats.quiz_mode: app/models/schemas.py QuizMode ("exam"/"chat"); nullable,
  so the constraint allows NULL.
- project_items.status: app/models/schemas.py VocabStatus
  (new/learning/mastered).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0053_check_constraints_enums"
down_revision: Union[str, None] = "0052_user_owned_cascades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guard against any pre-existing stray values before adding constraints,
    # same pattern as 0035. "vocabulary" is a write alias always normalised to
    # "language" on insert (also already done once in 0017) — repeat
    # defensively. Anything else unrecognised falls back to "general" (the
    # column's own server_default, and already the bucket the app hides from
    # list/detail via is_learning_product_kind) rather than being force-fit
    # into a learning kind it never actually was.
    op.execute("UPDATE projects SET kind = 'language' WHERE kind = 'vocabulary'")
    op.execute(
        "UPDATE projects SET kind = 'general' WHERE kind NOT IN ('language', 'trivia', 'general')"
    )

    op.create_check_constraint(
        "ck_memories_type",
        "memories",
        "type IN ('profile', 'preference', 'project', 'fact', 'focus')",
    )
    op.create_check_constraint(
        "ck_projects_kind",
        "projects",
        "kind IN ('language', 'trivia', 'general')",
    )
    op.create_check_constraint(
        "ck_projects_level",
        "projects",
        "level IN ('level1', 'level2', 'level3', 'level4', 'level5', 'level6')",
    )
    op.create_check_constraint(
        "ck_users_plan",
        "users",
        "plan IN ('free', 'pro')",
    )
    op.create_check_constraint(
        "ck_users_response_tone",
        "users",
        "response_tone IN ('funny', 'professional', 'casual', 'soft')",
    )
    op.create_check_constraint(
        "ck_chats_quiz_mode",
        "chats",
        "quiz_mode IS NULL OR quiz_mode IN ('exam', 'chat')",
    )
    op.create_check_constraint(
        "ck_project_items_status",
        "project_items",
        "status IN ('new', 'learning', 'mastered')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_project_items_status", "project_items", type_="check")
    op.drop_constraint("ck_chats_quiz_mode", "chats", type_="check")
    op.drop_constraint("ck_users_response_tone", "users", type_="check")
    op.drop_constraint("ck_users_plan", "users", type_="check")
    op.drop_constraint("ck_projects_level", "projects", type_="check")
    op.drop_constraint("ck_projects_kind", "projects", type_="check")
    op.drop_constraint("ck_memories_type", "memories", type_="check")
