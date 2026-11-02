"""A bare reaction to the last reply ("oh really?", "wow", "hmm"), and when the clock stays out.

Kept out of routing.py, which may not grow past its size baseline.
"""

from __future__ import annotations

from app.modules.chat.reply_meta import is_about_time
from app.modules.turn_reading.reactions import is_reaction_turn


def clock_is_relevant(lightweight: bool, text: str | None) -> bool:
    """Only a turn that asks for a time gets the clock; a greeting, ack or reaction does not."""
    return not (lightweight or is_reaction_turn(text)) or is_about_time(text)
