"""The asked part of a question: from its last question verb to the end of that sentence.

A binder reads the asked clause apart from the givens, so "find the speed" and "a speed of
3 m/s" are never the same phrase. A subject may add verbs of its own ("convert").
"""

from __future__ import annotations

import re

# A phrase naming the quantity itself ("how long"), not an ask before one.
# "how many" names the count that follows it, the way "how long" names a time.
_SELF_NAMING = ("how long", "how far", "how fast", "how high", "how deep", "how many", "how tall")

ASK_VERBS = re.compile(
    r"\b(?:find|calculate|compute|determine|work\s+out|estimate|evaluate|"
    r"what|"
    r"how\s+(?:long|far|fast|high|deep|much|many|tall))\b",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[?!]|\.(?:\s|$)")


def ask_clause(text: str, verbs: re.Pattern[str] = ASK_VERBS) -> str | None:
    """The last question's asked part: from its verb to the end of its sentence.

    "How long" and the like name the quantity themselves, so they are kept.
    None when the text asks nothing.
    """
    asks = list(verbs.finditer(text))
    if not asks:
        return None
    ask = asks[-1]
    self_naming = re.sub(r"\s+", " ", ask.group().lower()).startswith(_SELF_NAMING)
    start = ask.start() if self_naming else ask.end()
    end_match = _SENTENCE_END.search(text, start)
    return text[start : end_match.start() if end_match else len(text)]
