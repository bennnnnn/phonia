"""Text cut into overlapping pieces for embedding: a file's pages, a chat's messages."""

from __future__ import annotations


def chunk_text(text: str, *, chunk_chars: int = 900, overlap: int = 120) -> list[str]:
    # Guard against a misconfigured overlap >= chunk_chars: `start` would
    # never advance past the previous chunk's start, spinning forever on a
    # long document (pure CPU loop in the background indexing worker, no
    # await to time out on). Shipped defaults (900/120) are safe; this is a
    # footgun guard for a bad config value, not a correctness fix for today.
    if overlap >= chunk_chars:
        overlap = max(0, chunk_chars - 1)
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if len(cleaned) <= chunk_chars:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_chars)
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks
