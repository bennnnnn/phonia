"""The words that say what a line is about, for the follow-up rules.

``related_questions`` keeps a general follow-up on the user's topic with them,
``follow_up_thread`` tells a line that names a topic of its own from a short follow-up, and
``follow_up_ground`` reads the nouns a reply shares with a problem. All read a topic word
the same way: four Latin letters or more, accents included, and not a word every question
uses.
"""

from __future__ import annotations

import re

# Lower-case Latin letters with their accents (casefolded text): "pâte" is one word, not
# "p" and "te", and "différence" is not "rence".
LATIN = "a-zß-öø-ÿ\u0100-\u017f"
TOPIC_WORD = re.compile(rf"[{LATIN}]{{4,}}")
STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "again",
        "also",
        "because",
        "been",
        "before",
        "being",
        "best",
        "better",
        "could",
        "does",
        "doing",
        "each",
        "from",
        "have",
        "here",
        "into",
        "just",
        "know",
        "like",
        "make",
        "more",
        "most",
        "much",
        "need",
        "only",
        "other",
        "should",
        "some",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "thing",
        "things",
        "this",
        "what",
        "when",
        "where",
        "which",
        "while",
        "will",
        "with",
        "would",
        "your",
    }
)
# Words that ask about a problem, show it or measure it, and the chat's fillers: every
# line and every reply uses them, whatever it is about.
_ASKS_OR_SHOWS = """again another answer calculate change check correct different easier easy
explain explanation figure find give happen hard harder help instead matter mean method part
problem question quick same simple simpler simply solve step take teach tell took understand
wrong chart diagram draw equation example formula graph number picture plot result show table
value visual fast high long many often"""
_FILLERS = """actually anyway anything around cool even every first going gonna good great last
maybe next nice okay please real really right someone something still sure thank think until
very want well"""
NAMES_NO_TOPIC = frozenset(f"{_ASKS_OR_SHOWS} {_FILLERS}".split())
# Everyday measures: what a line is about ("next month for 4 days"), but no ground a reply
# shares with a problem ("3 hours" in a bike problem, "allow 6 hours" in a day plan).
MEASURES = frozenset("second minute hour day week month year percent degree".split())
# "doesn't" is "does", not the word "doesn"; "what's" is "what".
_CONTRACTION = re.compile(r"n't\b|'(?:s|re|ll|ve|m|d)\b")


def topic_words(text: str, pattern: re.Pattern[str] = TOPIC_WORD) -> frozenset[str]:
    """What ``text`` is about: its topic words, each without its plural "s", and none a
    question frame or a filler. ``text`` has straight apostrophes."""
    folded = _CONTRACTION.sub("", text.casefold())
    words = (w for w in pattern.findall(folded) if not _names_nothing(w))
    # "makes", "needs" and "others" are stop words once their "s" is off.
    return frozenset(word for word in map(_singular, words) if not _names_nothing(word))


def _names_nothing(word: str) -> bool:
    return word in STOP_WORDS or word in NAMES_NO_TOPIC


def _singular(word: str) -> str:
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word
