"""Word-overlap relevance for memory when no embedding answers.

A fact with no vector yet, or a turn whose query embed timed out, is matched by
the words it shares with the question. A match needs a real word in common:
"how should I structure auth" never pulls in "User plays chess".
"""

from __future__ import annotations

import re

from app.modules.memory.ops import normalize_memory_text

_TERM = re.compile(r"[a-z0-9][a-z0-9+#]*", re.IGNORECASE)
_MIN_TERM_CHARS = 4
# Question and filler words: shared, they say nothing about the topic.
_STOP_TERMS = frozenset(
    {
        "what",
        "whats",
        "which",
        "where",
        "when",
        "who",
        "whom",
        "whose",
        "why",
        "how",
        "should",
        "would",
        "could",
        "about",
        "with",
        "have",
        "your",
        "yours",
        "that",
        "this",
        "these",
        "those",
        "there",
        "their",
        "they",
        "them",
        "from",
        "into",
        "onto",
        "like",
        "just",
        "some",
        "more",
        "most",
        "best",
        "good",
        "know",
        "does",
        "tell",
        "please",
        "want",
        "need",
        "make",
        "help",
        "give",
        "really",
        "thing",
        "things",
        "user",
        "users",
        "also",
        "been",
        "being",
        "were",
        "will",
        "than",
        "then",
        "very",
        "much",
        "many",
        "each",
        "every",
        "here",
        "over",
        "only",
        "other",
        "same",
        "such",
        "still",
        "even",
        "again",
        "today",
        "right",
        "think",
        "maybe",
        "sure",
        "okay",
    }
)


def terms(text: str | None) -> set[str]:
    """Topic words of ``text``: four letters or more, plural folded, no filler."""
    found: set[str] = set()
    for raw in _TERM.findall(normalize_memory_text(text or "")):
        word = raw.lower()
        if len(word) > _MIN_TERM_CHARS and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        if len(word) >= _MIN_TERM_CHARS and word not in _STOP_TERMS:
            found.add(word)
    return found


def overlap(query_terms: set[str], text: str | None) -> int:
    """How many topic words ``text`` shares with the question."""
    if not query_terms:
        return 0
    return len(query_terms & terms(text))
