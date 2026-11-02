"""Point stored model choices at the October 2026 catalog.

Revision ID: 0108_model_aliases_oct_2026
Revises: 0107_plus_plan

Gemini 2.5 Flash is retiring, and the catalog replaced six aliases. Three have
a successor, renamed wherever a user stored them:

- gemini-flash → gpt-6-luna (Auto's everyday lane)
- glm-4-flash → glm-5.3-flash
- gpt-5.5 → gpt-6-sol

Three are gone: minimax-m2, qwen-plus and mercury-2.

``users.enabled_models`` (the Settings model switches) drops a removed model;
a list that removal leaves empty becomes NULL, the plan default with Auto on.
A removed ``users.default_model`` or ``chats.model`` becomes ``auto``.
``messages.model`` is left alone: it records which model wrote each reply.
"""

import json
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0108_model_aliases_oct_2026"
down_revision: Union[str, None] = "0107_plus_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RENAMED: dict[str, str] = {
    "gemini-flash": "gpt-6-luna",
    "glm-4-flash": "glm-5.3-flash",
    "gpt-5.5": "gpt-6-sol",
}
REMOVED: frozenset[str] = frozenset({"minimax-m2", "qwen-plus", "mercury-2"})


def _migrate_enabled(models: list[str], renamed: dict[str, str]) -> list[str] | None:
    """The switches after the rename, in their order, each once; None when none is left."""
    out: list[str] = []
    for model in models:
        if model in REMOVED:
            continue
        model = renamed.get(model, model)
        if model not in out:
            out.append(model)
    return out or None


def _migrate_alias(alias: str, renamed: dict[str, str]) -> str:
    if alias in REMOVED:
        return "auto"
    return renamed.get(alias, alias)


def _rewrite(renamed: dict[str, str]) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, enabled_models FROM users WHERE enabled_models IS NOT NULL")
    ).fetchall()
    for user_id, models in rows:
        if not isinstance(models, list):
            continue
        updated = _migrate_enabled(models, renamed)
        if updated == models:
            continue
        conn.execute(
            sa.text("UPDATE users SET enabled_models = CAST(:models AS jsonb) WHERE id = :id"),
            {"models": None if updated is None else json.dumps(updated), "id": user_id},
        )
    for old in sorted({*renamed, *REMOVED}):
        new = _migrate_alias(old, renamed)
        conn.execute(
            sa.text("UPDATE users SET default_model = :new WHERE default_model = :old"),
            {"new": new, "old": old},
        )
        conn.execute(
            sa.text("UPDATE chats SET model = :new WHERE model = :old"),
            {"new": new, "old": old},
        )


def upgrade() -> None:
    _rewrite(RENAMED)


def downgrade() -> None:
    # The removed models cannot come back; the renamed ones return to their old names.
    _rewrite({new: old for old, new in RENAMED.items()})
