"""Whether a message is only a reaction to the last reply."""

from __future__ import annotations

import re

from app.modules.turn_reading.routing import EMOJI
from app.services.text_normalize import collapse_ws

# A reaction says nothing to look up or work out. It is not a lightweight turn: "really?" after
# a solve is a challenge, "oh yeah" can accept an offer, and both need the full path. It only
# needs no clock: with nothing else to answer, a model read the freshest line of the prompt back.
_REACTION_WORDS = (
    r"oh really|really|seriously|oh wow|wow|whoa|hmm+|huh|ah|oh|ooh|i see|oh i see"
    r"|no way|interesting|is that so|is that right|oh okay|oh ok|oh yeah|oh nice|oh cool"
)


# Same thanks suffix as routing's light-turn patterns.
_REACTION = re.compile(
    rf"^(?:{_REACTION_WORDS})(?:[!?.…, ]+(?:thanks|thank you|thx))?[!?.… ]*$",
    re.IGNORECASE,
)


def is_reaction_turn(text: str | None) -> bool:
    """A bare reaction to the last reply: "oh really?", "wow", "hmm", "is that so?"."""
    cleaned = collapse_ws(EMOJI.sub(" ", text or ""))
    return bool(cleaned) and len(cleaned) <= 24 and _REACTION.match(cleaned) is not None
