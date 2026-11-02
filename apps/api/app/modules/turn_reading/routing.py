"""What a message says about the turn it starts: a confirmation, a reply to an offer, a
light turn (structure ticket ST-04). Personal turns are ``personal``'s."""

from __future__ import annotations

import re

from app.modules.turn_reading.lesson_flow import lesson_step
from app.services import time_context as time_context_service
from app.services.text_normalize import collapse_ws

# Patterns assume input was passed through ``collapse_ws`` (single spaces only).
_BROAD_SELF_QUESTION = re.compile(
    r"^(?:"
    r"who am i\??"
    r"|what am i\??"
    r"|tell me about me\??"
    r"|what do you know about me\??"
    r"|describe me\??"
    r"|what(?:'re| are) i like\??"
    r")[.!?]*$",
    re.IGNORECASE,
)


def is_broad_self_question(text: str) -> bool:
    """Broad identity questions — name only, no personal context dump."""
    cleaned = collapse_ws(text)
    if not cleaned or time_context_service.is_location_question(cleaned):
        return False
    return bool(_BROAD_SELF_QUESTION.match(cleaned))


# Social turns stand alone; replies answer whatever the assistant just said.
_SOCIAL_WORDS = (
    r"hi|hello|hey|hiya|yo|sup"
    r"|thanks|thank you|thx|ty"
    r"|bye|goodbye|cya|see ya"
    r"|lol|lmao|haha|hehe"
)


_REPLY_WORDS = (
    r"ok|okay|k|cool|nice|great|perfect|awesome"
    r"|got it|sounds good|makes sense|understood"
    r"|yes|no|go|yep|nope|sure"
)


_THANKS_TAIL = r"(?:[!?.…, ]+(?:thanks|thank you|thx))?[!?.… ]*$"


_LIGHTWEIGHT_TURN = re.compile(
    rf"^(?:{_SOCIAL_WORDS}|{_REPLY_WORDS}){_THANKS_TAIL}",
    re.IGNORECASE,
)


_SHORT_REPLY = re.compile(rf"^(?:{_REPLY_WORDS}){_THANKS_TAIL}", re.IGNORECASE)


# Accepting an offer — not a greeting. "no" / "thanks" / "hi" stay off this list.
_SHORT_CONFIRMATION = re.compile(
    r"^(?:"
    r"yes|yep|yeah|yup|yea|"
    r"sure(?: thing)?|"
    r"ok(?:ay)?|k|"
    r"go(?: ahead)?|"
    r"do it|please|proceed|"
    r"yes please|ok go"
    r")[!?.… ]*$",
    re.IGNORECASE,
)


# Phrase scan on the prior assistant tail (no regex over the body).
_OFFER_PHRASES = (
    "want me to",
    "shall i",
    "should i",
    "i can check",
    "i can look",
    "i can search",
    "i can draft",
    "i can write",
    "i can make",
    "i can draw",
    "i can show",
    "i can send",
    "i can find",
    "i can help",
    "i can do that",
    "i could",
    "happy to",
    "let me know",
    "if you'd like",
    "if you would like",
    "if you want",
)


def is_short_confirmation(text: str) -> bool:
    """True for yes / go / sure — not hi, thanks, or no."""
    cleaned = collapse_ws(text)
    if not cleaned:
        return False
    return bool(_SHORT_CONFIRMATION.match(cleaned))


def is_short_reply(text: str) -> bool:
    """True for yes / no / got it / understood — an answer to the last assistant turn.

    Unlike hi / thanks / bye, its meaning depends on what the assistant just
    said, so the turn needs the recent window ("Understood?" → "no").
    """
    cleaned = collapse_ws(text)
    if not cleaned:
        return False
    if is_short_confirmation(cleaned):
        return True
    return len(cleaned) <= 24 and bool(_SHORT_REPLY.match(cleaned))


def prior_looks_like_offer(prior_assistant: str | None) -> bool:
    """True when the last assistant turn offered to do something or asked a question."""
    if not prior_assistant:
        return False
    cleaned = collapse_ws(prior_assistant)
    if not cleaned:
        return False
    tail = cleaned[-400:].lower()
    if any(phrase in tail for phrase in _OFFER_PHRASES):
        return True
    if "?" in cleaned[-200:]:
        return True
    # A lesson step ends on a check question, even when its options trail it.
    return lesson_step(prior_assistant) is not None


# Emoji, flags, joiners ("hi 👋" is "hi"); of U+2300-23FF only the watch, hourglasses, keyboard
# and media buttons (⏳ stayed in homework), never maths brackets. Escapes, not characters.
EMOJI = re.compile(
    r"[\U0001f1e6-\U0001f1ff\U0001f300-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d"
    r"\u231a\u231b\u2328\u23cf\u23e9-\u23f3\u23f8-\u23fa]+"
)


def is_lightweight_chat_turn(
    text: str,
    *,
    prior_assistant: str | None = None,
) -> bool:
    """Ultra-brief social turns (hi / thanks / ok) — short reply style only.

    Memory / status theater is gated separately by ``needs_rich_context`` so we
    do not grow this allowlist for every casual phrase ("how is ur day", etc.).
    A short yes / no / got it after a question or an offer is an answer
    (follow-through, or "no" to "Understood?"), not a greeting.
    """
    cleaned = collapse_ws(text)
    if not cleaned:
        return True
    # "👍" alone is an acknowledgement; "hi 👋" is "hi".
    cleaned = collapse_ws(EMOJI.sub(" ", cleaned))
    if not cleaned:
        return True
    # Only real greetings (hi, ok, go). A short fragment stays with the
    # thread so the solver can keep the open problem.
    looks_light = len(cleaned) <= 24 and bool(_LIGHTWEIGHT_TURN.match(cleaned))
    if not looks_light:
        return False
    if is_short_reply(cleaned) and prior_looks_like_offer(prior_assistant):
        return False
    return True
