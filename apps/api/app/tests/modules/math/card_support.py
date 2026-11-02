"""How a direct reply ends: its working typeset above, the final answer alone in the card."""

from __future__ import annotations

from app.modules.math.tools.direct_working import typeset_working
from app.services.card_value import split_working


def card_with_working(equation: str, user_text: str) -> str:
    """The end of a direct reply whose checked line is ``equation``."""
    working, answer = split_working(equation)
    lead = "" if working is None else f"${typeset_working(working, user_text)}$\n\n"
    return f"{lead}```answer\n{answer}\n```\n"
