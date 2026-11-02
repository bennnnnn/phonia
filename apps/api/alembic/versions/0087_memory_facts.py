"""Atomic memory facts: drop one-row-per-type uniqueness.

Revision ID: 0087_memory_facts
Revises: 0085_attach_idx_cov

Keep the revision id at or under 32 chars — ``alembic_version.version_num``
is ``varchar(32)`` (see 0063).
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0087_memory_facts"
down_revision: Union[str, None] = "0085_attach_idx_cov"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AS_OF_PREFIX_RE = re.compile(r"^As of (\d{4}-\d{2}-\d{2}):\s*", re.IGNORECASE)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _keep_source_embedding(facts: list[str]) -> bool:
    """Keep the blob vector only when this row did not split into extra facts."""
    return len(facts) == 1


def _keeper_and_merged(items: Sequence[Any]) -> tuple[Any, str]:
    """One row per (user, type) for downgrade uniqueness — all statuses fold in."""
    keeper = max(
        items,
        key=lambda item: (
            1 if getattr(item, "status", "active") == "active" else 0,
            item.updated_at,
        ),
    )
    parts: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = " ".join((getattr(item, "text", None) or "").strip().split()).rstrip(".")
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
    return keeper, merged[:8000] or str(getattr(keeper, "text", "") or "")


def _strip_as_of(text: str) -> tuple[str, datetime | None]:
    match = _AS_OF_PREFIX_RE.match(text.strip())
    if not match:
        return text.strip(), None
    confirmed = datetime.fromisoformat(f"{match.group(1)}T00:00:00+00:00")
    return text.strip()[match.end() :].strip(), confirmed


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "memory_include_sensitive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "memories",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column(
        "memories",
        sa.Column("sensitivity", sa.String(), nullable=False, server_default="normal"),
    )
    op.add_column("memories", sa.Column("importance", sa.Numeric(3, 2), nullable=True))
    op.add_column(
        "memories",
        sa.Column(
            "last_confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "memories",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memories",
        sa.Column("superseded_by_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "memories",
        sa.Column("source_message_id", sa.UUID(), nullable=True),
    )
    op.create_index("ix_memories_user_status", "memories", ["user_id", "status"])
    op.create_index(
        "ix_memories_user_type_status",
        "memories",
        ["user_id", "type", "status"],
    )
    op.create_foreign_key(
        "fk_memories_superseded_by_id",
        "memories",
        "memories",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_memories_source_message_id",
        "memories",
        "messages",
        ["source_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_memories_status",
        "memories",
        "status IN ('active', 'superseded', 'muted')",
    )
    op.create_check_constraint(
        "ck_memories_sensitivity",
        "memories",
        "sensitivity IN ("
        "'normal', 'health', 'finance', 'legal', "
        "'relationship', 'identity', 'highly_sensitive'"
        ")",
    )
    op.drop_constraint("uq_memories_user_type", "memories", type_="unique")

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, user_id, type, text, confidence, source_chat_id, "
            "created_at, updated_at FROM memories ORDER BY user_id, type, updated_at ASC"
        )
    ).fetchall()
    for row in rows:
        body, as_of = _strip_as_of(row.text or "")
        facts = _split_sentences(body) or ([body] if body else [])
        if not facts:
            conn.execute(
                sa.text("DELETE FROM memories WHERE id = :id"),
                {"id": row.id},
            )
            continue
        first, *rest = facts
        if _keep_source_embedding(facts):
            conn.execute(
                sa.text(
                    "UPDATE memories SET text = :text, last_confirmed_at = COALESCE("
                    ":confirmed, updated_at) WHERE id = :id"
                ),
                {
                    "text": first,
                    "confirmed": as_of,
                    "id": row.id,
                },
            )
        else:
            conn.execute(
                sa.text(
                    "UPDATE memories SET text = :text, last_confirmed_at = COALESCE("
                    ":confirmed, updated_at), "
                    "embedding = NULL, embedding_json = NULL, embedding_text_hash = NULL "
                    "WHERE id = :id"
                ),
                {
                    "text": first,
                    "confirmed": as_of,
                    "id": row.id,
                },
            )
        for fact in rest:
            conn.execute(
                sa.text(
                    "INSERT INTO memories (id, user_id, type, text, confidence, "
                    "status, sensitivity, source_chat_id, created_at, updated_at, "
                    "last_confirmed_at) "
                    "VALUES (:id, :user_id, :type, :text, :confidence, "
                    "'active', 'normal', :source_chat_id, :created_at, :updated_at, "
                    "COALESCE(:confirmed, :updated_at))"
                ),
                {
                    "id": uuid.uuid4(),
                    "user_id": row.user_id,
                    "type": row.type,
                    "text": fact,
                    "confidence": row.confidence,
                    "source_chat_id": row.source_chat_id,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                    "confirmed": as_of,
                },
            )

    op.alter_column(
        "memories",
        "last_confirmed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Drop the self-FK first so folding inactive rows cannot violate it.
    op.drop_constraint("fk_memories_superseded_by_id", "memories", type_="foreignkey")
    rows = conn.execute(
        sa.text(
            "SELECT id, user_id, type, text, confidence, source_chat_id, "
            "created_at, updated_at, status FROM memories "
            "ORDER BY user_id, type, updated_at ASC"
        )
    ).fetchall()
    grouped: dict[tuple[object, str], list] = defaultdict(list)
    for row in rows:
        grouped[(row.user_id, row.type)].append(row)
    for (_user_id, _mem_type), items in grouped.items():
        if len(items) <= 1:
            continue
        keeper, merged = _keeper_and_merged(items)
        conn.execute(
            sa.text("UPDATE memories SET text = :text WHERE id = :id"),
            {"text": merged, "id": keeper.id},
        )
        for item in items:
            if item.id != keeper.id:
                conn.execute(sa.text("DELETE FROM memories WHERE id = :id"), {"id": item.id})

    op.drop_constraint("ck_memories_sensitivity", "memories", type_="check")
    op.drop_constraint("ck_memories_status", "memories", type_="check")
    op.drop_constraint("fk_memories_source_message_id", "memories", type_="foreignkey")
    op.drop_index("ix_memories_user_type_status", table_name="memories")
    op.drop_index("ix_memories_user_status", table_name="memories")
    op.drop_column("memories", "source_message_id")
    op.drop_column("memories", "superseded_by_id")
    op.drop_column("memories", "superseded_at")
    op.drop_column("memories", "last_confirmed_at")
    op.drop_column("memories", "importance")
    op.drop_column("memories", "sensitivity")
    op.drop_column("memories", "status")
    op.drop_column("users", "memory_include_sensitive")
    op.create_unique_constraint("uq_memories_user_type", "memories", ["user_id", "type"])
