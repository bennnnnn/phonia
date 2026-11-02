"""Finalize passes for the server's part of a multi-part reply.

"Switch to dark mode and tell me a joke": the model tells the joke and the settings
card goes under it. ``chat/finalize_passes.py`` lists the passes in order. The card
commits the text: ``done`` carries what it added, so a later pass's failure keeps it.
Each request the model answered in its own section is set off from the next by a
hairline.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.modules.chat.finalize_subjects import fallback_text
from app.modules.chat.turn_prep.reading import plan_of
from app.services.md_fence_scan import line_fences, strip_closed_fences

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

_SETTINGS_FENCE = "settings_proposal"


def add_settings_card(state: FinalizeState) -> str:
    """The server's settings card under the reply; a card the model wrote is not one."""
    card = state.ctx.settings_card
    if not isinstance(card, str) or not card:
        return state.text
    text = strip_closed_fences(state.text, _SETTINGS_FENCE).rstrip()
    text = f"{text}\n\n{card}" if text else card
    state.committed = fallback_text(text, server_text=state.server_text)
    return text


# "### Weather in Paris": one request's section. "---": the hairline between two.
_SECTION = re.compile(r"^#{2,3}\s+\S")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")


def divide_request_sections(state: FinalizeState) -> str:
    """A message that asks several things: a hairline between the requests' sections."""
    settings = state.settings
    plan = plan_of(state.ctx.user_message_content, settings)
    return divide_sections(state.text) if plan.multi else state.text


def divide_sections(text: str) -> str:
    """``---`` before every section heading but the first, unless one is there already."""
    out: list[str] = []
    seen = False
    for line, fence in zip(text.split("\n"), line_fences(text), strict=True):
        if fence is None and _SECTION.match(line):
            previous = next((kept for kept in reversed(out) if kept.strip()), "")
            if seen and not _RULE.match(previous):
                # A blank line first: "text" then "---" is a heading in markdown.
                out.extend(["", "---", ""] if out and out[-1].strip() else ["---", ""])
            seen = True
        out.append(line)
    return "\n".join(out)
