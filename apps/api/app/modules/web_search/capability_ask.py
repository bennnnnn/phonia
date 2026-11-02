"""A yes/no question about whether Recall searches: "can you search the web?".

"Show me how u work", then "Can you search the web?" (live chat, 2026-10-25): the
question read as a search request that names nothing, so the turn searched the line
before it and showed song lyrics. A question about the app asks nothing to look up;
the reply says what Recall can do. A request that names what to search ("can you
search for the latest news on Tesla?") or points at the chat ("can you look it up?",
"can you search the web for that?") is not this question and still searches. These
are the words alone: after a question it could not answer or an offer to search, the
same words ask for that search (``detection.asks_only_whether_it_searches``).

A positive grammar over tokens, no regex over chat text: an opener, a question lead,
one verb of searching and words that only say where or what kind ("the web", "things",
"online"). A word outside it leaves the message to the search rules.
"""

from __future__ import annotations

from app.modules.web_search.search_word import is_search_word
from app.services.text_normalize import collapse_ws, fold_token, straighten_apostrophes

Phrase = tuple[str, ...]

_OPENERS: tuple[Phrase, ...] = (
    ("thank", "you"),
    ("quick", "question"),
    ("just", "curious"),
    ("out", "of", "curiosity"),
    ("one", "more", "thing"),
    *(
        (word,)
        for word in (
            "hey",
            "hi",
            "hello",
            "yo",
            "oh",
            "so",
            "ok",
            "okay",
            "wait",
            "btw",
            "um",
            "hmm",
            "also",
            "and",
            "but",
            "thanks",
            "cool",
            "great",
            "nice",
        )
    ),
)
# "can you …?" asks what Recall does; "would you …" and "can't you …" ask it to.
_ABILITY_LEADS: tuple[Phrase, ...] = (
    ("is", "it", "possible", "for", "you", "to"),
    ("do", "you", "know", "how", "to"),
    ("are", "you", "able", "to"),
    ("are", "u", "able", "to"),
    ("r", "u", "able", "to"),
    ("are", "you", "allowed", "to"),
    ("are", "you", "capable", "of"),
    ("can", "you"),
    ("can", "u"),
    ("could", "you"),
    ("could", "u"),
    ("you", "can"),
    ("do", "you"),
    ("do", "u"),
)
_HAVE_LEADS: tuple[Phrase, ...] = (
    ("do", "you", "have"),
    ("do", "u", "have"),
    ("have", "you", "got"),
    ("you", "have"),
    ("does", "recall", "have"),
    ("does", "this", "app", "have"),
    ("is", "there"),
    ("are", "you", "connected", "to"),
)
_ADVERBS = frozenset({"actually", "even", "also", "really", "ever", "still"})
# Where a search goes, and the kind of thing it finds: never what to look up. "Now" is
# not one: "can you search the web now?" after a miss asks for the search.
_WHERE = frozenset({"web", "internet", "net", "online", "google"})
_FILLER = frozenset(
    {
        "the",
        "a",
        "an",
        "any",
        "on",
        "in",
        "for",
        "to",
        "things",
        "stuff",
        "anything",
        "something",
        "info",
        "information",
        "live",
        "real-time",
        "realtime",
        "too",
        "as",
        "well",
        "at",
        "all",
        "yet",
        "or",
        "not",
    }
)
# What "do you have …?" may name: the feature, never a topic.
_FEATURE = frozenset(
    {
        "search",
        "searching",
        "browsing",
        "browser",
        "access",
        "ability",
        "feature",
        "function",
        "tool",
        "tools",
        "capability",
        "connection",
        "engine",
        "browse",
    }
)
# The verbs of searching, and whether the rest must say where ("access the internet").
_VERBS: dict[str, bool] = {
    "google": False,
    "googling": False,
    "browse": False,
    "browsing": False,
    "surf": True,
    "access": True,
    "use": True,
    "go": True,
    "get": True,
}


def _strip(words: list[str], phrases: tuple[Phrase, ...]) -> tuple[list[str], bool]:
    """``words`` after one of ``phrases`` at their head, and whether one was there."""
    for phrase in phrases:
        if tuple(words[: len(phrase)]) == phrase:
            return words[len(phrase) :], True
    return words, False


def _only_where(rest: list[str], *, extra: frozenset[str] = frozenset()) -> bool:
    return all(w in _WHERE or w in _FILLER or w in extra for w in rest)


def _verb_phrase(words: list[str]) -> bool:
    """ "search the web", "google things", "look stuff up online", "access the internet" """
    if not words:
        return False
    head, rest = words[0], words[1:]
    if is_search_word(head):
        return _only_where(rest)
    if head == "look":
        return "up" in rest and _only_where(rest, extra=frozenset({"up"}))
    needs_where = _VERBS.get(head)
    if needs_where is None:
        return False
    if not _only_where(rest, extra=_FEATURE):
        return False
    return not needs_where or any(w in _WHERE or w in _FEATURE for w in rest)


def _names_the_feature(words: list[str]) -> bool:
    """ "web search", "internet access", "the ability to search the web" """
    vocabulary = _WHERE | _FILLER | _FEATURE
    return (
        bool(words)
        and all(w in vocabulary or w in _ADVERBS for w in words)
        and any(w in _WHERE or w in {"search", "searching", "browsing", "browser"} for w in words)
    )


def asks_whether_it_searches(text: str) -> bool:
    """The whole message asks whether Recall can search: "do you search online?"."""
    cleaned = straighten_apostrophes(collapse_ws(text))
    if not cleaned or len(cleaned) > 120:
        return False
    words = [w for w in (fold_token(word) for word in cleaned.split()) if w]
    opened = True
    while opened and words:
        words, opened = _strip(words, _OPENERS)
    rest, has = _strip(words, _HAVE_LEADS)
    if has:
        return _names_the_feature(rest)
    rest, ability = _strip(words, _ABILITY_LEADS)
    if not ability:
        return False
    while rest and rest[0] in _ADVERBS:
        rest = rest[1:]
    return _verb_phrase(rest)
