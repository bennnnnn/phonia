"""A learner stuck on a topic: "I don't understand recursion", "I'm confused about
pointers", "recursion makes no sense to me". Each asks to be taught that topic now.

The words after the cue decide it. A person, a question word or something in the last
reply is not a topic: "I don't understand why she left", "what you mean", "step 3",
"the second example". Text reaching here is collapsed and has straight apostrophes.
"""

from __future__ import annotations

import re

# The cue, then the topic: "i (still) don't understand ___", "i'm confused about ___".
# "Stuck" and "struggling" are left out: "stuck on the highway", "struggling with grief".
_STUCK_BEFORE = re.compile(
    r"\bi\s+(?:still\s+|really\s+|just\s+)?(?:don'?t|do\s+not|can'?t|cannot|never)\s+"
    r"(?:really\s+|fully\s+)?(?:get|understand|understood|grasp|follow)\s+"
    r"|\bi(?:'m|\s+am)\s+(?:so\s+|really\s+|still\s+|totally\s+)?"
    r"(?:confused\s+(?:about|by)|lost\s+(?:on|with))\s+"
    r"|\bcan'?t\s+wrap\s+my\s+head\s+around\s+",
    re.IGNORECASE,
)
# The topic, then the cue: "recursion makes no sense (to me)", "pointers confuse me".
_STUCK_AFTER = re.compile(
    r"(?:^|[.!?]\s)(?P<topic>[^.?!,]{2,60}?)\s+"
    r"(?:makes?\s+no\s+sense|confuses?\s+me|(?:is|are)\s+(?:so\s+)?confusing|"
    r"goes\s+over\s+my\s+head)\b",
    re.IGNORECASE,
)
# First words that do not start a topic: a question word, a person, the last reply.
_NOT_A_TOPIC = frozenset(
    {
        "it", "this", "that", "these", "those", "what", "why", "how", "when", "where", "who",
        "whom", "whose", "which", "whether", "if", "you", "your", "yours", "me", "my", "her",
        "him", "his", "she", "he", "they", "them", "their", "people", "anyone", "someone",
        "anything", "everything", "nothing", "step", "steps", "line", "lines", "part", "parts",
        "point", "question", "number", "example", "answer", "a", "an", "life", "love",
    }
)  # fmt: skip
# After "the": the last reply's parts, not a topic ("the second example", "the last step").
_NOT_A_TOPIC_AFTER_THE = frozenset(
    {
        "first", "second", "third", "fourth", "fifth", "last", "previous", "next", "above",
        "below", "same", "example", "examples", "answer", "explanation", "step", "steps",
        "part", "question", "reply", "code", "output", "result", "quiz", "world",
    }
)  # fmt: skip
_WORD = re.compile(r"[^\W\d_][\w'-]*")


def _names_a_topic(words: list[str]) -> bool:
    if not words:
        return False
    first = words[0].casefold()
    if first in _NOT_A_TOPIC:
        return False
    if first == "the":
        return len(words) > 1 and words[1].casefold() not in _NOT_A_TOPIC_AFTER_THE
    return True


def stuck_on_a_topic(cleaned: str) -> bool:
    """True when the user says a named topic is beyond them and wants it explained."""
    before = _STUCK_BEFORE.search(cleaned)
    if before is not None and _names_a_topic(_WORD.findall(cleaned[before.end() :])[:2]):
        return True
    after = _STUCK_AFTER.search(cleaned)
    return after is not None and _names_a_topic(_WORD.findall(after.group("topic"))[:2])
