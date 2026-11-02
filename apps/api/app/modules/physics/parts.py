"""How many things a question asks for, so an instant reply never drops one.

"A ball is dropped from 45 m. (a) How long does it take to hit the ground?
(b) How fast is it going when it lands?" was answered (b) alone, instantly, and
the model never saw the question, so (a) was never answered. A question whose
asks outnumber what the verified result answers goes to the model, with the
verified part as its block.
"""

from __future__ import annotations

import re

from app.modules.physics.ask import QUANTITY, SENTENCE, ask_clause
from app.modules.physics.claims import CHECK_ONLY
from app.modules.physics.schemas import PhysicsIntent
from app.services.law_binding.ask import ASK_VERBS
from app.services.question_parts import labelled_parts

# A second quantity joined to the first: "the deceleration and the braking force".
_JOINED = re.compile(
    r"\b(?:and|as\s+well\s+as|plus)\s+(?:also\s+)?(?:the\s+|its\s+|their\s+)?"
    r"(?:[\w-]+\s+){0,2}?(" + QUANTITY.pattern.removeprefix(r"\b") + ")",
    re.IGNORECASE,
)
# "and acceleration 4 m/s^2", "and a mass of 2 kg": a given's label, not an ask.
_LABELLED = re.compile(r"\s*(?:of|=|is|:|was)?\s*[-+]?\.?\d", re.IGNORECASE)
# A question word that opens an ask. One after "and", a comma or "then" opens a second
# ask in the same sentence: "how long until it hits the ground and how fast is it
# going?" was answered with the speed alone (2026-10-25), since the sentence's ask was
# read from its last question word.
_ASK_LEAD = re.compile(
    r"\bhow\s+(?:long|fast|far|high|much|many|quickly|big|heavy|hot|deep|strong|hard)\b"
    r"|\bwhat(?:'s|\s+is|\s+was|\s+will|\s+would|\s+are)\b|\bwhen\s+(?:does|do|will|is)\b"
    r"|\bwith\s+what\s+(?:speed|velocity|force|energy)\b",
    re.IGNORECASE,
)
_JOINS = re.compile(
    r"(?:,|;|&|\band\b|\bthen\b|\bas\s+well\s+as\b|\bplus\b)\s*(?:also\s+|then\s+)?$",
    re.IGNORECASE,
)


def _question_sentences(text: str) -> int:
    count = 0
    for sentence in SENTENCE.finditer(text):
        body = sentence.group()
        if CHECK_ONLY.match(body):
            continue
        if body.rstrip().endswith("?") or ASK_VERBS.search(body):
            count += 1
    return count


def _joined_quantities(text: str) -> int:
    clause = ask_clause(text)
    if clause is None:
        return 0
    joined = [
        match for match in _JOINED.finditer(clause) if not _LABELLED.match(clause, match.end(1))
    ]
    return 1 + len(joined)


def _joined_asks(text: str) -> int:
    """Asks in each sentence: its first question word, and each joined to it. The sentence
    need not end in "?": typed on a phone, "…how long until it hits the ground and how fast
    is it going" often doesn't."""
    count = 0
    for sentence in SENTENCE.finditer(text):
        body = sentence.group()
        leads = list(_ASK_LEAD.finditer(body))
        if leads:
            count += 1 + sum(1 for lead in leads[1:] if _JOINS.search(body[: lead.start()]))
    return count


def asks_count(text: str) -> int:
    """How many things the text asks for: labelled parts, questions, joined quantities
    or joined questions."""
    return max(
        labelled_parts(text),
        _question_sentences(text),
        _joined_quantities(text),
        _joined_asks(text),
        1,
    )


def answers_count(intent: PhysicsIntent) -> int:
    """How many asks a verified intent answers: its listed parts, or each asked kind."""
    return max(len(intent.requested_ops), len(intent.asked), 1)


def asks_more_than_answered(text: str, intent: PhysicsIntent) -> bool:
    return asks_count(text) > answers_count(intent)
