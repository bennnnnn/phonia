"""A question's labelled parts, for every subject: "(i) protons, (ii) neutrons, (iii) electrons".

A verified result answers one thing. A question in labelled parts asks several, so an
instant reply built from that one result drops the rest: "determine the number of
(i) protons, (ii) neutrons, (iii) electrons" was answered "N = 12" alone (2026-10-30).
"""

from __future__ import annotations

import re

# "(a)", "b)", "(ii)": a labelled part. Two or more distinct labels are parts.
_PART_LABEL = re.compile(r"(?:^|[\s,;:.?!])\(?([a-h]|i{1,3}|iv|vi{0,3})\)(?=\s)", re.IGNORECASE)

# Said to the model beside a verified result that answers one of those parts.
ONE_PART_NOTE = (
    "The question has more labelled parts than this verified result answers. "
    "Answer every part, in the question's order and under its own label, and use this "
    "result for its part."
)


def asks_more_parts(text: str, answers: str) -> bool:
    """``text`` has more labelled parts than ``answers`` has lines."""
    lines = [line for line in answers.splitlines() if line.strip()]
    return labelled_parts(text) > max(len(lines), 1)


def labelled_parts(text: str) -> int:
    """How many distinct part labels ``text`` has; 0 when fewer than two."""
    labels = {match.group(1).lower() for match in _PART_LABEL.finditer(text)}
    return len(labels) if len(labels) >= 2 else 0
