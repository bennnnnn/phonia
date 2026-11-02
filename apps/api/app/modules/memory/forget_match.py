"""Which saved fact a "forget …" or "stop mentioning …" line names.

The memory model decides first. When it names no fact, this backup matches the
phrase the user said, never a single word of it: "forget that I use React" drops
"User uses React", not "User builds Recall with React Native and FastAPI", and
"forget that I live in Nairobi" leaves "User's sister lives in Nairobi suburbs".
"""

from __future__ import annotations

import re

from app.modules.memory.ops import normalize_memory_text

_WORD = re.compile(r"[a-z0-9][a-z0-9+#.']*", re.IGNORECASE)
# The user speaking about themselves: "I live in …", "my dog …".
_SELF_WORDS = frozenset({"i", "i'm", "im", "i've", "ive", "i'd", "me", "my", "mine", "myself"})
# Function words a phrase and a fact can differ in without naming another fact.
_STOP_WORDS = frozenset(
    {
        *_SELF_WORDS,
        "a",
        "an",
        "the",
        "that",
        "this",
        "these",
        "those",
        "about",
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "to",
        "in",
        "on",
        "at",
        "of",
        "and",
        "or",
        "with",
        "for",
        "from",
        "it",
        "its",
        "please",
        "really",
        "you",
        "your",
        "anymore",
        "again",
        "now",
        "just",
        "also",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "thing",
        "things",
        "stuff",
        "fact",
        "answers",
        "replies",
        "chats",
        "user",
        "user's",
    }
)
# A fact about someone else ("User's sister lives in Nairobi") is not what
# "forget that I live in Nairobi" names.
_OTHER_PEOPLE = frozenset(
    {
        "sister",
        "brother",
        "sibling",
        "mom",
        "mum",
        "mother",
        "dad",
        "father",
        "parent",
        "wife",
        "husband",
        "partner",
        "spouse",
        "son",
        "daughter",
        "kid",
        "child",
        "children",
        "baby",
        "friend",
        "boss",
        "manager",
        "colleague",
        "coworker",
        "cousin",
        "aunt",
        "uncle",
        "grandma",
        "grandmother",
        "grandpa",
        "grandfather",
        "girlfriend",
        "boyfriend",
        "fiance",
        "fiancee",
        "family",
        "roommate",
        "neighbor",
        "neighbour",
    }
)


def phrase_names_fact(phrase: str, fact_text: str) -> bool:
    """True when every content word of ``phrase`` is in the fact, as the same name.

    "React" inside "React Native" is another name; a fact about the user's sister
    is not named by a phrase about the user.
    """
    said = _words(phrase)
    if not said:
        return False
    about_user = said[0].lower() in _SELF_WORDS
    wanted = {_stem(word) for word in said if word.lower() not in _STOP_WORDS}
    wanted.discard("")
    if not wanted:
        return False
    fact_words = _words(normalize_memory_text(fact_text))
    stems = [_stem(word) for word in fact_words]
    if not wanted <= set(stems):
        return False
    if about_user and (set(stems) & _OTHER_PEOPLE) - wanted:
        return False
    return not _inside_longer_name(fact_words, stems, wanted)


def names_nothing(phrase: str) -> bool:
    """True when the phrase has no word of its own: "please", "it again"."""
    return all(word.lower() in _STOP_WORDS for word in _words(phrase))


def _inside_longer_name(words: list[str], stems: list[str], wanted: set[str]) -> bool:
    for index, stem in enumerate(stems):
        if stem not in wanted:
            continue
        for near in (index - 1, index + 1):
            # The fact's first word is capitalised as a sentence, not as a name.
            if near <= 0 or near >= len(words):
                continue
            neighbour = words[near]
            if neighbour[:1].isupper() and stems[near] not in wanted:
                return True
    return False


def _words(text: str) -> list[str]:
    return [word.rstrip(".'") for word in _WORD.findall(text or "") if word.rstrip(".'")]


def _stem(word: str) -> str:
    lowered = word.lower()
    if lowered.endswith("'s"):
        lowered = lowered[:-2]
    if len(lowered) > 3 and lowered.endswith("s") and not lowered.endswith("ss"):
        lowered = lowered[:-1]
    return lowered
