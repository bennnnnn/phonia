"""What a chat turn's prompt carries: recent window, history compression and RAG, to-dos."""

from pydantic import BaseModel


class ChatContextSettings(BaseModel):
    # Chat-history semantic RAG (pgvector over past turns; top-k at turn start).
    # Never dumps the full transcript — Golden Rule 3. Recent-window ids are
    # excluded so this complements memory + summary, not duplicates them.
    chat_history_rag_enabled: bool = True
    chat_history_rag_chunk_limit: int = 6
    chat_history_rag_min_similarity: float = 0.30
    chat_history_rag_chunk_chars: int = 900
    chat_history_rag_chunk_overlap: int = 120
    chat_history_rag_max_chunks_per_message: int = 6
    # A search ranks the user's newest chunks only (exactly, no vector index); older
    # chunks are deleted as new ones are stored (``chunks_repository.prune_beyond_window``).
    chat_history_rag_search_window: int = 2000
    recent_message_window: int = 20  # hard cap on verbatim messages
    link_preview_cache_ttl: int = 3600
    todo_inject_limit: int = 100
    # A reminder change from chat is a card the user taps to save (or mark
    # done, move, delete). Off: chat writes to-dos as soon as it reads them.
    todo_prompt_limit: int = 48

    # History compression — keep recent turns verbatim within a token budget,
    # summarise everything older. At 6000 a chat building an HTML page kept only its
    # last version and the new request (each version ~5,900 tokens), and every earlier
    # request lived in an 800-token summary (2026-10-29). 16000 keeps about three
    # versions, and an ordinary chat whole to the 20-message cap. Every model alias
    # reads 128k or more.
    history_compression_enabled: bool = True
    context_token_budget: int = 16_000
    history_summary_batch: int = 10
    history_summary_urgent_pending: int = 3
    summary_max_tokens: int = 800

    # Claim check — on a searched reply, a claim the sources and the user's messages do not
    # support is cut before it saves (``modules/chat/claim_check.py``). Off: replies as written.
    claim_check_enabled: bool = True
    claim_check_timeout_seconds: float = 8.0
