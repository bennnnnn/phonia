"""Finalize passes for the server's part of a multi-part reply.

"Switch to dark mode and tell me a joke": the model tells the joke and the settings
card goes under it. "Draw a cat wearing a hat and also explain black holes": the
picture drawn beside the answer goes above it, or a line says why it could not.
``chat/finalize_passes.py`` lists them in order. Both commit the text: ``done``
carries what they added, so a later pass's failure keeps it. Each request the model
answered in its own section is set off from the next by a hairline.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.modules.chat.finalize_subjects import fallback_text
from app.modules.chat.turn_prep.reading import plan_of
from app.modules.images.reply_picture import ReplyPicture
from app.services.md_fence_scan import line_fences, strip_closed_fences

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

_SETTINGS_FENCE = "settings_proposal"


async def attach_reply_picture(state: FinalizeState) -> str:
    """The picture above the reply. A stopped reply draws nothing (its slot comes back)."""
    ctx = state.ctx
    picture = ctx.reply_picture
    if not isinstance(picture, ReplyPicture):
        return state.text
    if state.was_cancelled or (state.should_cancel is not None and state.should_cancel()):
        picture.cancel()
        return state.text
    text, ids = await picture.attach(state.text)
    # After the answer photo's pass, which sets the list: the picture is linked beside it.
    ctx.answer_photo_ids = [*ctx.answer_photo_ids, *ids]
    state.committed = fallback_text(text, server_text=state.server_text)
    return text


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
