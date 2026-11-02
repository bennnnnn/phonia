"""What may stand before a percent: a question stem and at most one stated operation.

"Subtract 5 from 25% of 80" is 25% of 80 - 5; read from the percent alone it verified 20.
So did "halve 25% of 80" and "the square root of 25% of 80", and "Is 15 less than 25% of
80?" asks a comparison, not a sum (2026-10-31, the model reader's translated questions
and their review). The clause that holds the percent is read only when it is fully read:
a stem from the list below, then one of "subtract A from", "take A (away) from", "A
subtracted from", "add A to", "A more/less than", or nothing. Anything else declines.
Earlier clauses of the sentence are its setting ("Out of 250 people, what is 30% of 80?")
unless they do arithmetic of their own.
"""

from __future__ import annotations

import re

from app.services.number_text import DECIMAL

# The ways a question asks for the value.
_STEM = (
    r"(?:(?:please|so|ok|okay|hey)\s+)*"
    r"(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
    r"(?:(?:tell\s+me|work\s+out|find|calculate|compute|evaluate|determine"
    r"|what\s+(?:is|was|will\s+be|would\s+be)|what's|whats|how\s+much\s+is|what\s+number\s+is"
    r"|what\s+is\s+(?:obtained|the\s+result)\s+(?:by|when\s+you|if\s+you|of)"
    r"|what\s+(?:do|will|would)\s+you\s+(?:get|obtain)\s+(?:by|when\s+you|if\s+you))\s+)?"
)
# The one operation the percent may be the first operand of.
_LEAD = (
    rf"(?:(?P<take>subtract(?:ing)?|tak(?:e|ing)(?:\s+away)?)\s+\$?(?P<taken>{DECIMAL})"
    r"\s+(?:away\s+)?from"
    rf"|\$?(?P<subtracted>{DECIMAL})\s+(?:subtracted|taken\s+away)\s+from"
    rf"|(?P<add>add(?:ing)?)\s+\$?(?P<added>{DECIMAL})\s+to"
    rf"|\$?(?P<compared>{DECIMAL})\s+(?P<than>less|fewer|more)\s+than)\s+"
)
_CLAUSE = re.compile(rf"\s*{_STEM}(?:{_LEAD})?(?:the\s+)?", re.IGNORECASE)
# Arithmetic in an earlier clause makes the percent a term of it ("If you subtract 5 from
# it, what is 25% of 80?").
_ARITHMETIC_BEFORE = re.compile(
    r"[+*/^=\u00d7\u00f7\u2212]|(?<![A-Za-z])-|-(?![A-Za-z])|\b(?:subtract\w*|minus|plus|"
    r"add|adds|added|adding|sum|difference|product|quotient|times|multipl\w*|divid\w*|away|"
    r"less|fewer|more|increase\w*|decrease\w*|twice|double|triple|half)\b",
    re.IGNORECASE,
)
# Where the sentence that holds the percent begins, and where its clauses do.
_SENTENCE_END = re.compile(r"[.?!;:](?=\s|$)|\n")
_CLAUSE_END = re.compile(r",(?=\s)")


def leading_addend(cleaned: str, rate_start: int) -> tuple[bool, float | None]:
    """Whether the words before the percent are fully read, and the addend they give."""
    head = cleaned[:rate_start]
    ends = [match.end() for match in _SENTENCE_END.finditer(head)]
    head = head[ends[-1] if ends else 0 :]
    clauses = [match.end() for match in _CLAUSE_END.finditer(head)]
    setting, own = head[: clauses[-1] if clauses else 0], head[clauses[-1] if clauses else 0 :]
    if _ARITHMETIC_BEFORE.search(setting):
        return False, None
    read = _CLAUSE.fullmatch(own)
    if read is None:
        return False, None
    if read.group("take"):
        return True, -float(read.group("taken"))
    if read.group("subtracted"):
        return True, -float(read.group("subtracted"))
    if read.group("add"):
        return True, float(read.group("added"))
    if read.group("compared"):
        amount = float(read.group("compared"))
        return True, amount if read.group("than").lower() == "more" else -amount
    return True, None
