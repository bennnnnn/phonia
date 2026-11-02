"""Personal memory: extraction cadence, injection limits, semantic recall, caches."""

from pydantic import BaseModel


class MemorySettings(BaseModel):
    semantic_memory_enabled: bool = True
    memory_min_confidence: float = 0.4
    memory_inject_limit: int = 15
    memory_active_fact_cap: int = 150
    # Untouched stale vectors embedded per apply pass. Touched rows always
    # embed; leftover NULLs wait for a later pass instead of bursting 150
    # HTTP calls on the first write after migration.
    memory_embed_backfill_per_pass: int = 16
    # Hard cap on formatted memory block chars injected into the system prompt.
    memory_inject_max_chars: int = 1500
    memory_cache_ttl: int = 300
    memory_query_cache_ttl: int = 120
    # Run memory extraction every N completed assistant turns (always on turn 1,
    # and always on an explicit remember/forget). Default 1 so a fact stated on
    # turn 2 is not dropped if the chat ends there. Ops can raise this to skip
    # intermediate LLM cost; skipped lines still land on the next pass via the
    # extract cursor.
    memory_extract_every_n_turns: int = 1
    memory_query_embed_cache_ttl: int = 3600
    # Chat-path live embed budget, for memory and chat-history recall: a slow
    # embedding provider falls back to the type-priority memory block (and no
    # earlier-chat snippets) instead of holding the first token. The embed runs
    # on and fills the cache for the next turn. Document search waits longer
    # (attachments/rag.py): a question about a file needs its excerpts. Background
    # jobs use background_llm_timeout_seconds.
    memory_query_embed_timeout_seconds: float = 0.75
    # Minimum cosine similarity for fact/focus/project injection (0 = disabled).
    # profile/preference always inject; 0.35 keeps off-topic sections out.
    memory_min_similarity: float = 0.35
