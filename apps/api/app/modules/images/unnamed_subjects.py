"""Photo subjects that name nothing on their own: a count with nothing counted.

"can u show me both" after water and carbon dioxide searched the word "both" and showed a
"Both is good" meme (2026-10-25). "both", "all of them", "the other two", "all 3" and
"both side by side, please" are read from the chat instead. Every word must be a count
word, a number, or a known tail; "both sides of a coin" and "all the planets" name what
to search.
"""

from __future__ import annotations

from app.services.text_normalize import fold_token

_COUNT_WORDS = frozenset(
    {
        "both",
        "all",
        "each",
        "either",
        "neither",
        "two",
        "three",
        "four",
        "five",
        "other",
        "others",
        "one",
        "ones",
        "them",
        "those",
        "these",
        "em",
    }
)
_JOINERS = frozenset({"of", "the"})
# How to show them, not what: "both at night", "all of them side by side".
_TAIL_PHRASES = (
    ("side", "by", "side"),
    ("next", "to", "each", "other"),
    ("at", "night"),
    ("up", "close"),
    ("in", "real", "life"),
    ("together",),
    ("please",),
    ("pls",),
    ("plz",),
    ("again",),
    ("too",),
    ("now",),
)


def _without_tails(words: list[str]) -> list[str]:
    trimmed = True
    while trimmed:
        trimmed = False
        for tail in _TAIL_PHRASES:
            if len(words) > len(tail) and tuple(words[-len(tail) :]) == tail:
                words = words[: -len(tail)]
                trimmed = True
    return words


def is_count_only(subject: str) -> bool:
    """True when *subject* counts things it does not name ("both", "the 3 of them")."""
    words = _without_tails([fold_token(word) for word in subject.split()])
    if not any(word in _COUNT_WORDS for word in words):
        return False
    return all(word in _COUNT_WORDS or word in _JOINERS or word.isdigit() for word in words)
