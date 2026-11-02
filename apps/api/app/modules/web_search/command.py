"""Read an explicit request to search the web: "do a search", "google it", "search for X".

The whole message must be the request; a cue inside a longer question is
``patterns._EXPLICIT_SEARCH``'s job. Token scans only, no regex over chat text.

``SearchCommand.subject`` is None when the request names nothing to search
("do a search", "look it up", "check that online"): the conversation says what.
Whether "can you search the web?" asks about Recall or for a search depends on the chat
before it: ``detection.asks_only_whether_it_searches`` reads it there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.web_search.search_word import is_search_word
from app.services.text_normalize import collapse_ws, fold_token, straighten_apostrophes


@dataclass(frozen=True)
class SearchCommand:
    subject: str | None


_LEAD_PHRASES: tuple[tuple[str, ...], ...] = (
    ("why", "don't", "you"),
    ("why", "dont", "you"),
    ("i", "want", "you", "to"),
    ("i", "need", "you", "to"),
    ("go", "ahead", "and"),
    ("can", "you"),
    ("could", "you"),
    ("would", "you"),
    ("will", "you"),
    ("can", "u"),
    # "Can't you look it up? You looked up the weather" (live chat, 2026-10-25).
    ("can't", "you"),
    ("cant", "you"),
    ("can't", "u"),
    ("cant", "u"),
    ("couldn't", "you"),
    ("couldnt", "you"),
    ("could", "u"),
    ("pls",),
    ("plz",),
    ("please",),
    ("ok",),
    ("okay",),
    ("so",),
    ("then",),
    ("and",),
    ("now",),
    ("just",),
    ("try", "to"),
)
_TRAILING_FILLERS = frozenset({"please", "pls", "plz", "now", "again", "quickly", "then"})
_ONLINE_TAILS: tuple[tuple[str, ...], ...] = (
    ("on", "the", "internet"),
    ("on", "the", "web"),
    ("on", "google"),
    ("on", "line"),
    ("the", "internet"),
    ("the", "web"),
    ("online",),
    ("internet",),
    ("web",),
)
_ARTICLES = frozenset({"a", "an", "another", "one", "some", "the"})
_SEARCH_ADJECTIVES = frozenset({"web", "online", "internet", "google", "quick", "new", "live"})
_SUBJECT_PREPOSITIONS = frozenset({"for", "on", "about", "of"})
# A request that points back at the conversation rather than naming a topic.
_REFERENCE_WORDS = frozenset(
    {
        "it",
        "that",
        "this",
        "them",
        "him",
        "her",
        "those",
        "these",
        "there",
        "one",
        "something",
        "more",
        "info",
        "information",
        "details",
        "again",
        "up",
    }
)
# "search engine optimization tips" asks about search, not for one.
_SEARCH_NOUN_HEADS = frozenset(
    {
        "engine",
        "engines",
        "algorithm",
        "algorithms",
        "bar",
        "box",
        "function",
        "functions",
        "query",
        "queries",
        "result",
        "results",
        "history",
        "term",
        "terms",
        "field",
        "button",
        "feature",
        "console",
        "page",
        "filter",
        "and",
        "or",
        "in",
        "vs",
        "versus",
        "optimization",
        "tree",
        "trees",
        "space",
        "party",
        "parties",
        "warrant",
        "warrants",
        "light",
        "lights",
        "string",
        "strings",
        "method",
        "methods",
        "index",
        "api",
        "binary",
        "linear",
        "problem",
        "problems",
    }
)
# "search my emails" / "search for my keys" ask about the user's own things.
_PERSONAL_WORDS = frozenset({"my", "our", "mine", "me", "i"})
# "fact check that claim", "search for that name": still the conversation's topic.
_GENERIC_NOUNS = frozenset(
    {
        "claim",
        "fact",
        "facts",
        "answer",
        "info",
        "information",
        "name",
        "story",
        "thing",
        "stuff",
        "question",
        "statement",
        "topic",
        "word",
        "person",
        "place",
    }
)
_DEMONSTRATIVES = frozenset({"that", "this", "the", "those", "these", "it", "his", "her", "their"})
_MAX_COMMAND_WORDS = 14
_MAX_BARE_SUBJECT_WORDS = 8


def _strip_lead(words: list[str]) -> list[str]:
    changed = True
    while changed and words:
        changed = False
        for phrase in _LEAD_PHRASES:
            n = len(phrase)
            if len(words) > n and tuple(words[:n]) == phrase:
                words = words[n:]
                changed = True
                break
    return words


def _strip_tail(words: list[str]) -> tuple[list[str], bool]:
    """Drop trailing fillers; report whether the request said online / the web."""
    online = False
    changed = True
    while changed and words:
        changed = False
        if words[-1] in _TRAILING_FILLERS:
            words = words[:-1]
            changed = True
            continue
        if len(words) >= 2 and words[-2:] == ["for", "me"]:
            words = words[:-2]
            changed = True
            continue
        for tail in _ONLINE_TAILS:
            n = len(tail)
            if len(words) > n and tuple(words[-n:]) == tail:
                words = words[:-n]
                online = changed = True
                break
    return words, online


_ONLINE_HEADS: tuple[tuple[str, ...], ...] = (
    ("on", "the", "internet"),
    ("on", "the", "web"),
    ("in", "the", "internet"),
    ("on", "google"),
    ("the", "internet"),
    ("the", "web"),
    ("the", "net"),
    ("online",),
    ("google",),
)


def _strip_online_head(folded: list[str], original: list[str]) -> tuple[list[str], list[str]]:
    """ "the web for X" -> "for X": where to search is not what to search."""
    for head in _ONLINE_HEADS:
        n = len(head)
        if len(folded) >= n and tuple(folded[:n]) == head:
            return folded[n:], original[n:]
    return folded, original


def _subject(folded: list[str], original: list[str]) -> str | None:
    """None for a reference ("it", "that", nothing); the original words otherwise."""
    if not folded or all(w in _REFERENCE_WORDS or w in _ARTICLES for w in folded):
        return None
    if folded[0] in _DEMONSTRATIVES and all(w in _GENERIC_NOUNS for w in folded[1:]):
        return None
    return " ".join(original).strip(" ?.!,") or None


def _after_preposition(folded: list[str], original: list[str]) -> SearchCommand | None:
    if not folded:
        return SearchCommand(subject=None)
    if folded[0] in _SUBJECT_PREPOSITIONS:
        return SearchCommand(subject=_subject(folded[1:], original[1:]))
    return None


def _match_do_a_search(folded: list[str], original: list[str]) -> SearchCommand | None:
    """ "do / run a [quick|web|online] search [for X]" """
    if not folded or folded[0] not in {"do", "run", "make", "perform", "try"}:
        return None
    i = 1
    if i < len(folded) and folded[i] in _ARTICLES:
        i += 1
    while i < len(folded) and folded[i] in _SEARCH_ADJECTIVES:
        i += 1
    if i >= len(folded) or not is_search_word(folded[i]):
        return None
    rest, rest_original = _strip_online_head(folded[i + 1 :], original[i + 1 :])
    return _after_preposition(rest, rest_original)


def _match_search(folded: list[str], original: list[str], *, online: bool) -> SearchCommand | None:
    """ "search", "search it", "search for X", "search up X", "search X online" """
    if not folded or not is_search_word(folded[0]):
        return None
    rest, rest_original = folded[1:], original[1:]
    if rest and rest[0] == "up":
        rest, rest_original = rest[1:], rest_original[1:]
    rest, rest_original = _strip_online_head(rest, rest_original)
    if not rest or all(w in _REFERENCE_WORDS for w in rest):
        return SearchCommand(subject=None)
    by_preposition = _after_preposition(rest, rest_original)
    if by_preposition is not None:
        return by_preposition
    if rest[0] in _SEARCH_NOUN_HEADS:
        return None
    if not online and len(rest) > _MAX_BARE_SUBJECT_WORDS:
        return None
    return SearchCommand(subject=_subject(rest, rest_original))


def _match_google(folded: list[str], original: list[str]) -> SearchCommand | None:
    """ "google it", "google the meaning of bini", "google for X" """
    if not folded or folded[0] not in {"google", "bing"}:
        return None
    rest, rest_original = folded[1:], original[1:]
    by_preposition = _after_preposition(rest, rest_original)
    if by_preposition is not None:
        return by_preposition
    return SearchCommand(subject=_subject(rest, rest_original))


def _match_look_up(folded: list[str], original: list[str], *, online: bool) -> SearchCommand | None:
    """ "look it up", "look up X", "look X up", "look online", "look for X online" """
    if not folded or folded[0] != "look":
        return None
    rest, rest_original = folded[1:], original[1:]
    # "Look up to your parents" admires; it searches nothing.
    if rest[:2] == ["up", "to"]:
        return None
    if rest and rest[0] == "up":
        return SearchCommand(subject=_subject(rest[1:], rest_original[1:]))
    if rest and rest[-1] == "up":
        return SearchCommand(subject=_subject(rest[:-1], rest_original[:-1]))
    if online:
        if not rest:
            return SearchCommand(subject=None)
        if rest[0] in {"for", "into", "at"}:
            return SearchCommand(subject=_subject(rest[1:], rest_original[1:]))
    return None


def _match_check_online(
    folded: list[str], original: list[str], *, online: bool
) -> SearchCommand | None:
    """ "check online", "verify that online", "find it online", "fact check it" """
    if not folded:
        return None
    head = folded[0]
    if head in {"fact-check", "factcheck"} or folded[:2] == ["fact", "check"]:
        skip = 1 if head != "fact" else 2
        return SearchCommand(subject=_subject(folded[skip:], original[skip:]))
    if head == "browse":
        rest, rest_original = folded[1:], original[1:]
        if rest and rest[0] == "for":
            return SearchCommand(subject=_subject(rest[1:], rest_original[1:]))
        return SearchCommand(subject=None) if not rest else None
    if not online or head not in {"check", "verify", "confirm", "find"}:
        return None
    rest, rest_original = folded[1:], original[1:]
    if rest and rest[0] in {"out", "for"}:
        rest, rest_original = rest[1:], rest_original[1:]
    return SearchCommand(subject=_subject(rest, rest_original))


def _match_use_search(folded: list[str]) -> SearchCommand | None:
    """ "use web search", "use google", "use the internet" """
    if not folded or folded[0] != "use":
        return None
    rest = [w for w in folded[1:] if w not in _ARTICLES]
    if rest and (is_search_word(rest[-1]) or rest[-1] in {"google", "internet", "web"}):
        return SearchCommand(subject=None)
    return None


def search_command(text: str) -> SearchCommand | None:
    """The search the whole message asks for, or None when it asks something else."""
    cleaned = straighten_apostrophes(collapse_ws(text))
    if not cleaned or len(cleaned) > 200:
        return None
    original = cleaned.split()
    folded = [fold_token(w) for w in original]
    if len(folded) > _MAX_COMMAND_WORDS:
        return None
    keep = [i for i, w in enumerate(folded) if w]
    original = [original[i] for i in keep]
    folded = [folded[i] for i in keep]

    stripped = _strip_lead(folded)
    original = original[len(folded) - len(stripped) :]
    folded, online = _strip_tail(stripped)
    original = original[: len(folded)]
    if online and not folded:
        return None

    for match in (
        lambda: _match_do_a_search(folded, original),
        lambda: _match_search(folded, original, online=online),
        lambda: _match_google(folded, original),
        lambda: _match_look_up(folded, original, online=online),
        lambda: _match_check_online(folded, original, online=online),
        lambda: _match_use_search(folded),
    ):
        command = match()
        if command is None:
            continue
        if (
            command.subject
            and not online
            and any(fold_token(w) in _PERSONAL_WORDS for w in command.subject.split())
        ):
            return None
        return command
    return None


_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def asks_to_search(text: str) -> bool:
    """A sentence of the message is a search request: "Can't you look it up? You looked up
    the weather" asks for one, though its second sentence says why."""
    return any(
        search_command(part) is not None
        for part in _SENTENCE_BREAK.split(collapse_ws(text))
        if part
    )
