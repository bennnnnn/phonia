"""Lines that each open with a bold lead stay separate lines.

A model lists options one per line with single breaks ("🇨🇭 **Switzerland — best for
quality of life** (…)", then "🇩🇪 **Germany — …**"), and Markdown joins single breaks into
one paragraph, so the options ran together. A run of two or more such lines becomes one
paragraph each. A lead may follow emoji or flags; list items, headings, quotes, tables and
indented lines are left alone (twin: apps/mobile/lib/markdown/leadLines.ts).
"""

from __future__ import annotations

import unicodedata

from app.modules.chat.markdown_regions import map_prose_outside_fences

# What may come before the bold lead: emoji, flags, their modifiers and joiners, spaces.
_PREFIX_CATEGORIES = frozenset({"So", "Sk", "Mn", "Cf"})
_MAX_PREFIX = 16


def _opens_with_bold_lead(line: str) -> bool:
    """``**Lead**`` (or ``🇨🇭 **Lead**``) at the start of an unindented line."""
    start = line.find("**")
    if start < 0 or start > _MAX_PREFIX or line[:1] == " ":
        return False
    if any(
        char != " " and unicodedata.category(char) not in _PREFIX_CATEGORIES
        for char in line[:start]
    ):
        return False
    close = line.find("**", start + 2)
    return close > start + 2


def _separate(prose: str) -> str:
    lines = prose.split("\n")
    out: list[str] = []
    for index, line in enumerate(lines):
        if index and _opens_with_bold_lead(line) and _opens_with_bold_lead(lines[index - 1]):
            out.append("")
        out.append(line)
    return "\n".join(out)


def separate_lead_lines(text: str) -> str:
    """Each line of a run of bold-lead lines becomes its own paragraph."""
    return map_prose_outside_fences(text, _separate)
