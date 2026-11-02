"""One memory summary paragraph per user and type

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-28
"""

from collections import defaultdict
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _merge_texts(texts: list[str]) -> str:
    seen: set[str] = set()
    parts: list[str] = []
    for raw in texts:
        clean = " ".join(raw.strip().split()).rstrip(".")
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(clean)
    merged = ". ".join(parts)
    if merged and not merged.endswith("."):
        merged += "."
    return merged[:8000]


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, user_id, type, text, confidence, source_chat_id, created_at, updated_at "
            "FROM memories ORDER BY user_id, type, updated_at ASC"
        )
    ).fetchall()

    grouped: dict[tuple, list] = defaultdict(list)
    for row in rows:
        grouped[(row.user_id, row.type)].append(row)

    for (_user_id, _mem_type), items in grouped.items():
        if len(items) <= 1:
            continue
        keeper = max(items, key=lambda r: r.updated_at)
        merged = _merge_texts([item.text for item in items])
        conn.execute(
            sa.text("UPDATE memories SET text = :text, updated_at = NOW() WHERE id = :id"),
            {"text": merged or keeper.text, "id": keeper.id},
        )
        for item in items:
            if item.id != keeper.id:
                conn.execute(sa.text("DELETE FROM memories WHERE id = :id"), {"id": item.id})

    op.drop_constraint("uq_memories_user_type_text", "memories", type_="unique")
    op.create_unique_constraint("uq_memories_user_type", "memories", ["user_id", "type"])


def downgrade() -> None:
    op.drop_constraint("uq_memories_user_type", "memories", type_="unique")
    op.create_unique_constraint(
        "uq_memories_user_type_text",
        "memories",
        ["user_id", "type", "text"],
    )
