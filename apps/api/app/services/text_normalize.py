"""Shared text normalization helpers."""

from __future__ import annotations

_HEAD_TAIL_SEP = "\n…\n"
# Zero-width / BOM — iOS sometimes leaves these on a two-letter greeting.
_FORMAT_CHARS = frozenset("\u200b\u200c\u200d\ufeff\u2060")
_DROP_FORMAT_CHARS = dict.fromkeys(map(ord, _FORMAT_CHARS))


def collapse_ws(text: str) -> str:
    """Collapse runs of whitespace so matchers need no ``\\s+`` (avoids ReDoS).

    A turn asks this of its message a hundred times or more, so each looks for the format
    characters with ``in`` (a C search); ``isdisjoint`` hashed every character instead.
    """
    if (
        "\u200b" in text
        or "\u200c" in text
        or "\u200d" in text
        or "\ufeff" in text
        or "\u2060" in text
    ):
        text = text.translate(_DROP_FORMAT_CHARS)
    return " ".join(text.split())


def fold_token(word: str) -> str:
    """Lowercase and strip edge punctuation so ``tips,`` matches ``tips``."""
    return word.lower().strip(".,!?;:\"'()[]")


def straighten_apostrophes(text: str) -> str:
    """U+2018 and U+2019 become ``'``, so a rule written for "What's" reads the curly form.

    Smart punctuation (on by default on the iPhone keyboard) types them. ``replace`` is a
    C copy; a ``translate`` table looked up every character of a non-ASCII message.
    """
    return text.replace("\u2018", "'").replace("\u2019", "'")


def cap_text_head_tail(text: str, max_chars: int = 4000) -> str:
    """Keep the start and end of long text; drop the middle with an ellipsis marker."""
    if max_chars < 1 or len(text) <= max_chars:
        return text
    if max_chars <= len(_HEAD_TAIL_SEP):
        return text[:max_chars]
    budget = max_chars - len(_HEAD_TAIL_SEP)
    head = budget // 2
    tail = budget - head
    return f"{text[:head]}{_HEAD_TAIL_SEP}{text[-tail:]}"
