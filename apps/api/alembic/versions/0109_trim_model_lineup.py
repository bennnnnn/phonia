"""Drop the coding and frontier models from the catalog.

Revision ID: 0109_trim_model_lineup
Revises: 0108_model_aliases_oct_2026

Recall is not a coding assistant, so the expensive coding and frontier models
leave the catalog: gpt-6-sol, kimi-k3, minimax-m3, glm-5.3 and llama-70b.
qwen-3.8-max goes too; OpenRouter no longer lists it, so picking it failed.

``users.enabled_models`` (the Settings model switches) drops a removed model;
a list that removal leaves empty becomes NULL, the plan default with Auto on.
A removed ``users.default_model`` or ``chats.model`` becomes ``auto``.
``messages.model`` is left alone: it records which model wrote each reply.
GPT-6 Luna stays, as a paid model; the free plan's everyday model is now
qwen-3.7-flash, which needs no stored change.
"""

import json
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0109_trim_model_lineup"
down_revision: Union[str, None] = "0108_model_aliases_oct_2026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REMOVED: frozenset[str] = frozenset(
    {"gpt-6-sol", "kimi-k3", "qwen-3.8-max", "minimax-m3", "glm-5.3", "llama-70b"}
)


def _kept(models: list[str]) -> list[str] | None:
    """The switches without the removed models, in order; None when none is left."""
    out = [model for model in models if model not in REMOVED]
    return out or None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, enabled_models FROM users WHERE enabled_models IS NOT NULL")
    ).fetchall()
    for user_id, models in rows:
        if not isinstance(models, list):
            continue
        kept = _kept(models)
        if kept == models:
            continue
        conn.execute(
            sa.text("UPDATE users SET enabled_models = CAST(:models AS jsonb) WHERE id = :id"),
            {"models": None if kept is None else json.dumps(kept), "id": user_id},
        )
    for old in sorted(REMOVED):
        conn.execute(
            sa.text("UPDATE users SET default_model = 'auto' WHERE default_model = :old"),
            {"old": old},
        )
        conn.execute(sa.text("UPDATE chats SET model = 'auto' WHERE model = :old"), {"old": old})


def downgrade() -> None:
    # A removed model cannot come back: the earlier catalog still lists it, so
    # Settings can turn it on again by hand.
    pass
