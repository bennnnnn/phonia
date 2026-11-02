"""The profile name is the user's name: a saved fact that names them otherwise stays out.

The account name (``users.name``, Settings → Profile) is what the prompt calls the user.
On an account named Dev, saved memory held "User's name is Sam; they are a nursing
student living in Chicago": replies switched between the two names, apologised for
the switch, and once told the user that "the memory block" named a different person
(live chats, 2026-10-25). A fact line that states a different name is left out of the
memory block every prompt reads, so the prompt holds one name.

What a fact names, and what agrees, is ``user_name``. Selection already keeps such a
fact out of the identity slot (``facts.identity_core``); this filter runs on the block
text after its cache, so a fact the query brings in is dropped too, and a renamed
profile takes effect on the next turn.
"""

from __future__ import annotations

import re

from app.modules.memory.facts import SECTION_LABELS
from app.modules.memory.user_name import names_another_person

_PROFILE_HEADING = f"## {SECTION_LABELS['profile']}"
# The notes ``facts._fact_line`` adds after a fact: "(said 2026-10)", "(unconfirmed)".
_LINE_NOTES = re.compile(r" \((?:said \d{4}-\d{2})?(?:, )?(?:unconfirmed)?\)$")


def without_conflicting_names(block: str, profile_name: str | None) -> str:
    """The memory block without a Profile line that names the user differently."""
    if not block or _PROFILE_HEADING not in block or not isinstance(profile_name, str):
        return block
    lines = block.split("\n")
    kept: list[str] = []
    in_profile = False
    for line in lines:
        if line.startswith("## "):
            in_profile = line.strip() == _PROFILE_HEADING
        elif in_profile and line.startswith("- "):
            fact = _LINE_NOTES.sub("", line[2:].strip())
            if names_another_person(fact, profile_name):
                continue
        kept.append(line)
    return block if len(kept) == len(lines) else _without_empty_sections(kept)


def _without_empty_sections(lines: list[str]) -> str:
    """Drop a heading left with no facts under it, and the block when none are left."""
    out: list[str] = []
    for index, line in enumerate(lines):
        if line.startswith("## ") and not _has_fact_after(lines, index):
            if out and not out[-1].strip():
                out.pop()
            continue
        out.append(line)
    if not any(line.startswith("- ") for line in out):
        return ""
    return "\n".join(out)


def _has_fact_after(lines: list[str], heading: int) -> bool:
    for line in lines[heading + 1 :]:
        if line.startswith("## "):
            return False
        if line.startswith("- "):
            return True
    return False
