"""A short "What?" right after a reply: the user did not follow it.

After a Spanish reply in an English app, "What?" got "Gd: good, or something else?"
(2026-10-24): the model read it as a message it could not make out and copied the example
the unclear-message rule gives. "What?", "huh?", "what do you mean", "I don't get it" right
after a reply say one thing: say it again so they follow.

Not "what!" or "sorry" (surprise, an apology), "hmm" (thinking), "What's that?" or "what
does that mean?" (a term in the reply, or a photo sent with it), "What time is it?" (a
question of its own), or a message with no reply before it. Text is read as the iPhone
types it: curly apostrophes and doubled spaces.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.services.text_normalize import collapse_ws, straighten_apostrophes

_END = r"[\s?!.]*$"
# Phrases in English: the reply comes back in English.
_ENGLISH = re.compile(
    r"^(?:wh?at\s*\?|what do you mean|come again|say (?:that|it) again|sorry\s*\?|"
    r"i don'?t (?:get|understand)(?: (?:it|that|this|you))?|i'?m (?:lost|confused)|"
    rf"(?:that|this) makes no sense){_END}",
    re.IGNORECASE,
)
# Said in many languages ("Pardon ?", "Eh?", "Hm?", "??"): the reply keeps its language.
_ANY_LANGUAGE = re.compile(rf"^(?:huh\s*\?|eh\s*\?|hm+\s*\?|pardon\s*\?|\?+){_END}", re.IGNORECASE)

REPLY_MISSED_HINT = (
    "The user did not follow your last reply. Say it again so they can: simpler and shorter, "
    "the main point first, and if it may have been wrong, check it first. Do not ask what "
    "they meant."
)
# "What?" after a Spanish reply to English messages wanted English, and a reply told only
# "their latest message's language" kept the Spanish.
_IN_ENGLISH = "Write it in English, the language of their message."


def reply_missed_hint(query: str, prior: Sequence[tuple[str, str]]) -> str | None:
    """The note for "What?" and its kind right after a reply, or None."""
    if not any(role == "assistant" and text.strip() for role, text in prior):
        return None
    text = collapse_ws(straighten_apostrophes(query)).strip()
    if _ENGLISH.match(text):
        return f"{REPLY_MISSED_HINT} {_IN_ENGLISH}"
    return REPLY_MISSED_HINT if _ANY_LANGUAGE.match(text) else None


# "How" right after a reply asks how it was reached: after "Answer: 16.09344 km", a bare
# "How" got "Did you mean how the conversion works, or were you still typing?"
# (2026-10-29), the unclear-message rule read it as a message cut off.
_ASKS_HOW = re.compile(
    r"^(?:how|why|how so|how come|why so|why is that|how(?: did| do) (?:you|u) (?:get|know)"
    r"(?: (?:that|this|it))?|explain(?: (?:that|this|it))?|show me how|"
    r"show (?:your|the) (?:work|working|steps))(?: (?:tho|though|pls|please))?"
    rf"{_END}",
    re.IGNORECASE,
)
REPLY_HOW_HINT = (
    "The user asks how your last reply got its answer. Explain it: the steps or reasoning "
    "that lead to it, briefly, the main point first. Do not ask what they meant."
)


def reply_how_hint(query: str, prior: Sequence[tuple[str, str]]) -> str | None:
    """The note for a bare "How?" or "Why?" right after a reply that answered, or None.

    A reply that ended on its own question ("Should we use Redis?") gets "Why" as an
    answer to it, and a bare "show me" after "Want me to work it out?" is a yes: neither
    asks how a reply was reached.
    """
    last = next((text for role, text in reversed(prior) if role == "assistant"), "")
    if not last.strip() or last.rstrip().endswith("?"):
        return None
    text = collapse_ws(straighten_apostrophes(query)).strip()
    return REPLY_HOW_HINT if _ASKS_HOW.match(text) else None
