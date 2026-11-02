"""The couldn't-verify sentence a reply may carry: removed, never added.

``append_unverified_math_note`` runs on every reply, on the event loop
(``chat/finalize_subjects.append_unverified_notes``); ``math.fence`` exports it.
"""

from __future__ import annotations

import re

# The disclaimer, italic or plain, alone or at the end of the answer, with the blanks
# and the one ``*`` after it. Those before it are found by stepping back from it
# (``_phrase_start``): a pattern that opened with ``[ \t]*\*?[ \t]*`` retried every
# split of a run of spaces at every start in it, cubic in the run (800 spaces took 2 s).
_UNVERIFIED_PHRASE = re.compile(
    r"(?i)"
    r"(?:"
    r"i could(?:n't| not) (?:automatically )?verify this(?: result)?\.?"
    r"|couldn't verify this with sympy\.?"
    r"|this (?:result|answer) (?:is|was) not verified\.?"
    r")"
    r"[ \t]*\*?[ \t]*"
)


def _phrase_start(text: str, start: int, floor: int) -> int:
    """Where the blanks, one ``*`` and blanks before a phrase at ``start`` begin."""
    while start > floor and text[start - 1] in " \t":
        start -= 1
    if start > floor and text[start - 1] == "*":
        start -= 1
        while start > floor and text[start - 1] in " \t":
            start -= 1
    return start


def _without_unverified_phrases(text: str) -> str:
    pieces: list[str] = []
    cursor = 0
    for match in _UNVERIFIED_PHRASE.finditer(text):
        pieces.append(text[cursor : _phrase_start(text, match.start(), cursor)])
        cursor = match.end()
    pieces.append(text[cursor:])
    return "".join(pieces)


def append_unverified_math_note(content: str) -> str:
    """Remove a couldn't-verify sentence. Never add one.

    This runs on every reply, including one the solver did not check. A
    verified reply shows a check. Nothing in the chat says the result was
    not verified.
    """
    if not content or not content.strip():
        return content
    plain = content.replace("\u2019", "'")
    without = _without_unverified_phrases(plain)
    return re.sub(r"\n{3,}", "\n\n", without).strip()
