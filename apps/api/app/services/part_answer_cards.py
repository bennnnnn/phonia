"""Each part of an answer in its own card, under its own ``**Answer (a)**`` heading.

A reply in parts ("**Answer (a)** … **Answer (b)** …") had no card at all when the server
solved none of them: only one closing ``**Answer**`` heading is carded, so a crane's
energy and power sat on the phone as plain lines (2026-10-30). A part the server did not
verify gets the same card a one-part answer does, without the check.
"""

from __future__ import annotations

import re

from app.services.answer_fence import ANSWER_FENCE_LANGS, answer_heading, land_answer_card
from app.services.md_fence_scan import iter_fences, line_fences

PART_ANSWER_HEADING = re.compile(r"^\s*(?:#{1,4}\s+)?\*\*Answer \((?P<letter>[a-h])\):?\*\*:?\s*$")
_SECTION_HEADING = "**Answer**"


def _cards(text: str) -> int:
    return sum(fence.opener.lang in ANSWER_FENCE_LANGS for fence in iter_fences(text))


def _closing(lines: list[str], prose: list[int], last: int) -> int:
    """Where the reply's closing Answer starts after the last part, or the end. An Answer
    line directly under the last part's heading ("**Answer:** $v = 19.6$") is that part's
    own answer: a closing one follows something the part wrote (review, 2026-10-30)."""
    written = False
    for number in range(last + 1, len(lines)):
        if written and number in prose and answer_heading(lines[number]) is not None:
            return number
        written = written or bool(lines[number].strip())
    return len(lines)


def land_part_answer_cards(text: str) -> str | None:
    """``text`` with each part's final value in a card under its Answer heading; None
    unless the reply answers in two or more parts and a part gained a card.

    A part already carded stays as it is, and so does whatever follows the parts under a
    closing Answer heading ("**Answer:** It lands after 2 s.", "## Answer"): a summary,
    never one part's answer. A heading inside a code block is an example, not a part.
    """
    lines = text.split("\n")
    prose = [number for number, owner in enumerate(line_fences(text)) if owner is None]
    headings = [number for number in prose if PART_ANSWER_HEADING.match(lines[number])]
    if len(headings) < 2:
        return None
    out = lines[: headings[0]]
    closing = _closing(lines, prose, headings[-1])
    for start, end in zip(headings, [*headings[1:], closing], strict=True):
        # The part's heading read as the one Answer heading of its own section.
        section = land_answer_card("\n".join([_SECTION_HEADING, *lines[start + 1 : end]]), None)
        landed = section.split("\n")
        landed[landed.index(_SECTION_HEADING)] = lines[start].strip()
        out.extend(landed)
    out.extend(lines[closing:])
    joined = "\n".join(out)
    return joined if _cards(joined) > _cards(text) else None
