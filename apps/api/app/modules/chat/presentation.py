"""Assistant Markdown presentation: REPL transcripts, boundaries, then calculation rows.

The finalize pass, the direct replies and live talk run it before a reply is saved, so a
persisted assistant row is already presented. The phone shows rows saved from its
``SERVER_PRESENTATION_CUTOVER`` as saved and presents only the text still streaming and
older rows. Its twin is ``apps/mobile/lib/markdown/presentation.ts``;
docs/fixtures/presentation_cases.json holds both to the same output.
"""

from __future__ import annotations

import re

from app.modules.chat.calculation_layout import layout_calculations
from app.modules.chat.inline_boundaries import repair_inline_token_boundaries
from app.modules.chat.lead_lines import separate_lead_lines
from app.modules.chat.notation_spans import code_notation
from app.modules.chat.repl_transcript import fence_repl_transcripts
from app.services.answer_fence import (
    ANSWER_FENCE_LANGS,
    UNCHECKED_ANSWER_MARKER,
    VERIFIED_ANSWER_MARKER,
)
from app.services.md_fence_scan import iter_fences

_WHY_QUESTION = re.compile(r"\b(?:why|explain)\b", re.IGNORECASE)
_BARE_NUMBER_LINE = re.compile(r"\d+(?:\.\d+)?")


def _without_leading_number_card(reply: str) -> str:
    """The reply without an answer card that opens it holding only a number."""
    fence = next(iter_fences(reply), None)
    if fence is None or fence.start or not fence.closed or fence.lang not in ANSWER_FENCE_LANGS:
        return reply
    rows = [row.strip() for row in reply[fence.body_start : fence.body_end].split("\n")]
    checks = (VERIFIED_ANSWER_MARKER, UNCHECKED_ANSWER_MARKER)
    rows = [row for row in rows if row and row.lower() not in checks]
    if len(rows) != 1 or not _BARE_NUMBER_LINE.fullmatch(rows[0]):
        return reply
    return reply[fence.end :]


def drop_orphan_leading_answer(reply: str, user_text: str) -> str:
    """A why-question with no digits does not open with the previous sum.

    Tapping "why are positive sums larger?" after 3 + 4 = 7 used to print
    that 7 on its own line, then the explanation.
    """
    if not reply or not user_text or any(char.isdigit() for char in user_text):
        return reply
    if _WHY_QUESTION.search(user_text) is None:
        return reply
    text = _without_leading_number_card(reply).lstrip()
    lines = text.split("\n")
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index < len(lines) and _BARE_NUMBER_LINE.fullmatch(lines[index].strip()):
        text = "\n".join(lines[index + 1 :]).strip()
    return text


def present_assistant_markdown(text: str) -> str:
    """Fence REPL transcripts, keep notation as code, repair closed inline tokens, then
    split calculations."""
    if not text:
        return text
    prose = separate_lead_lines(code_notation(fence_repl_transcripts(text)))
    return layout_calculations(repair_inline_token_boundaries(prose))
