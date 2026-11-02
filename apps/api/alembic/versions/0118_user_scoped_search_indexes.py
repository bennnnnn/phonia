"""Index the searches by user; drop the indexes no query can use.

Revision ID: 0118_user_scoped_search_indexes
Revises: 0117_reminder_due_indexes

- Vector search. pgvector filters *after* an HNSW scan, which returns 40 candidates
  from every user's rows: a per-user chat-history or document search came back empty
  at scale, or the planner compared every vector the user ever stored. Searches now
  rank a bounded set of the user's (or the chat's) newest chunks exactly, so the three
  global HNSW indexes go; ``memories`` never ran a vector query at all.
  ``(user_id, created_at)`` serves the chat-history search's window.
- Text search. A trigram index over every user's messages handed the search other
  users' rows to recheck; ``btree_gin`` lets one index lead with ``user_id``.
- Prefix duplicates: a btree whose columns lead another's serves no query the longer
  one cannot, and every turn's inserts paid for it.

Dropping an index never breaks the previous release's queries, so this is one release.
Built and dropped CONCURRENTLY so writes keep flowing.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0118_user_scoped_search_indexes"
down_revision: Union[str, None] = "0117_reminder_due_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CREATE = (
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_message_chunks_user_created "
    "ON message_chunks (user_id, created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_messages_user_content_trgm "
    "ON messages USING gin (user_id, content gin_trgm_ops)",
)
# Index, and the statement that rebuilds it on downgrade.
_DROP = (
    (
        "ix_message_chunks_embedding",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_message_chunks_embedding "
        "ON message_chunks USING hnsw (embedding vector_cosine_ops)",
    ),
    (
        "ix_attachment_chunks_embedding",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_attachment_chunks_embedding "
        "ON attachment_chunks USING hnsw (embedding vector_cosine_ops)",
    ),
    (
        "ix_memories_embedding",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_memories_embedding "
        "ON memories USING hnsw (embedding vector_cosine_ops)",
    ),
    (
        "ix_messages_content_trgm",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_messages_content_trgm "
        "ON messages USING gin (content gin_trgm_ops)",
    ),
    (
        "ix_messages_chat_created",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_messages_chat_created "
        "ON messages (chat_id, created_at)",
    ),
    (
        "ix_message_chunks_user",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_message_chunks_user "
        "ON message_chunks (user_id)",
    ),
    (
        "ix_message_chunks_message",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_message_chunks_message "
        "ON message_chunks (message_id)",
    ),
    (
        "ix_todo_user_topic",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_todo_user_topic ON todo_items (user_id, topic)",
    ),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
    with op.get_context().autocommit_block():
        for statement in _CREATE:
            op.execute(statement)
        for name, _rebuild in _DROP:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for _name, rebuild in reversed(_DROP):
            op.execute(rebuild)
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_messages_user_content_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_message_chunks_user_created")
