"""Whether a message goes on with a recent draft."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.modules.turn_reading.routing import is_lightweight_chat_turn
from app.modules.turn_reading.writing_kind import (
    _DIRECT_REQUEST_INTRO,
    writing_request_kind,
)
from app.modules.turn_reading.writing_locales import is_locale_draft_change
from app.modules.turn_reading.writing_purpose import is_underspecified_writing_request
from app.services.draft_fences import draft_langs
from app.services.text_normalize import collapse_ws

_KIND_FENCE = {"email": "email", "message": "message", "social": "social"}


# A short follow-up that changes a draft: "make it more polite", "shorter",
# "add that I'll be back tomorrow", "another version", "translate it to Spanish",
# or says what it is for: "asking money", "about her birthday", "send it".
_DRAFT_FOLLOWUP = re.compile(
    r"^(?:(?:ok(?:ay)?|now|and|also|then|great|perfect|nice|thanks|cool)[,!.]?\s+)*"
    + _DIRECT_REQUEST_INTRO
    + r"(?:"
    r"(?:make|keep|get) (?:it|this|that)\b|"
    r"(?:(?:a )?(?:bit|little|lot|much|way) )?(?:more|less) [a-z]+|"
    r"(?:shorter|longer|simpler|clearer|friendlier|warmer|softer|nicer|politer|"
    r"formal|informal|casual|polite|professional)\b|"
    r"(?:add|remove|drop|include|mention|change|replace|say|use|put|swap|cut|delete|"
    r"take out|leave out|tone (?:it |this )?(?:down|up)|sign|end|start|open)\b|"
    r"(?:rewrite|redo|rephrase|reword|shorten|lengthen|polish|soften|simplify|"
    r"try again|again)\b|"
    r"(?:another|a different|a new|different|other) (?:version|one|draft|option|way)|"
    r"(?:give|write|show|send) (?:me )?(?:another|a different|a new|one more|more|other) "
    r"(?:versions?|ones?|drafts?|options?)|"
    r"translate (?:it|this|that)\b|"
    # "translate to Spanish", "now in French please": nothing new to translate.
    r"translate (?:in)?to [a-z]+(?: please| pls)?[.!?]*$|"
    r"(?:in|into) [a-z]+(?: (?:please|pls|instead|too))?[.!?]*$|"
    r"with(?:out)? (?:any |the |an? )?(?:emojis?|hashtags?|subject|greeting|signature)|"
    # What the draft is for, as the answer to "what should it say?"
    r"(?:it should |it'?s |tell (?:her|him|them) )?"
    r"(?:asking|ask(?:ing)? (?:for|about|if|her|him|them)|about|saying|telling|regarding|"
    r"wishing|thanking|inviting|apologi[sz]ing|reminding|letting|that (?:i|i'm|i'll|we))\b|"
    # "send it", "write the message", "send the email to her"
    r"(?:send|text|email|write|draft|show me|give me) "
    r"(?:it|this|that|(?:the|my|that|this) (?:message|text|email|draft|post|one))\b"
    r")",
    re.IGNORECASE,
)


# "Email", "as a text", "make it a facebook post": the same draft in another form.
_FORMAT_SWITCH = re.compile(
    r"^" + _DIRECT_REQUEST_INTRO + r"(?:"
    r"(?:make|turn|convert|change|rewrite|redo|write|send) (?:it|this|that)(?: (?:in)?to| as)? |"
    r"(?:send it |write it )?(?:as|in(?:to)?|via|by) "
    r")?(?:an? )?"
    r"(e-?mail|text(?: message)?|sms|message|facebook(?: post)?|linkedin(?: post)?|"
    r"tweet|instagram(?: caption| post)?)"
    r"(?: (?:version|format|instead|please))?[.!?]*$",
    re.IGNORECASE,
)


_FORMAT_FENCE = {
    "email": "email",
    "e-mail": "email",
    "text": "message",
    "text message": "message",
    "sms": "message",
    "message": "message",
    "facebook": "facebook",
    "facebook post": "facebook",
    "linkedin": "linkedin",
    "linkedin post": "linkedin",
    "tweet": "twitter",
    "instagram": "instagram",
    "instagram caption": "instagram",
    "instagram post": "instagram",
}


_FOLLOWUP_MAX_WORDS = 30


# A draft three exchanges back is still the one being talked about.
_FOLLOWUP_LOOKBACK = 6


# A longer question, or a long answer with no draft, moves the talk on.
_NEW_TOPIC_WORDS = 7


_NEW_TOPIC_ANSWER_CHARS = 400


def could_continue_draft(text: str | None) -> bool:
    """True when *text* reads like a change to a draft ("Email", "make it shorter").

    Cheap and history-free: ``draft_followup`` then checks the conversation.
    """
    if not text:
        return False
    cleaned = collapse_ws(text)
    if not cleaned or len(cleaned.split()) > _FOLLOWUP_MAX_WORDS:
        return False
    if _FORMAT_SWITCH.match(cleaned):
        return True
    kind = writing_request_kind(cleaned)
    if kind == "prose":
        return False
    if kind in _KIND_FENCE:
        return is_underspecified_writing_request(cleaned)
    return _DRAFT_FOLLOWUP.search(cleaned) is not None or is_locale_draft_change(cleaned)


def draft_followup(
    text: str | None, prior_messages: Sequence[tuple[str, str]] | None
) -> tuple[str, bool] | None:
    """(fence, drafted) when this line goes on with a recent draft, else None.

    The draft is the last one in a fenced reply, or else the last email, message or
    post the user asked for, within the last three exchanges. A new draft request
    with its own purpose ("write a message to my mom saying...") starts over.
    """
    if not prior_messages or not text:
        return None
    answered = _answers_draft_question(text, prior_messages)
    if answered is not None:
        return answered, False
    if not could_continue_draft(text):
        return None
    switch = _FORMAT_SWITCH.match(collapse_ws(text))
    found = _draft_in_history(prior_messages)
    if found is None or switch is None:
        return found
    # "Email" after a text message: the same draft, now in an ```email fence.
    return _FORMAT_FENCE[switch.group(1).lower()], found[1]


# An answer to "what should it say?" may run on: "the heater broke last night and…".
_ANSWER_MAX_WORDS = 60


# "Never mind" drops the draft, and "what should I say?" asks back: neither answers.
_DROPS_DRAFT = re.compile(
    r"^(?:never ?mind|forget (?:it|about it)|cancel|skip it|no thanks|nah|don'?t worry)\b",
    re.IGNORECASE,
)


_ASKS_BACK = re.compile(r"^(?:what|how|why|which|who|where|when)\b.*\?$", re.IGNORECASE)


def _answers_draft_question(text: str, prior_messages: Sequence[tuple[str, str]]) -> str | None:
    """The fence of the draft the last reply asked about, when this line answers it.

    "Write a message to my landlord", "What should it say?", then "the heater is
    broken": whatever the user says next is what the draft says.
    """
    if len(prior_messages) < 2:
        return None
    (asker, asked), (replier, reply) = prior_messages[-2], prior_messages[-1]
    if asker != "user" or replier != "assistant" or "?" not in reply:
        return None
    if draft_langs(reply) or len(reply) > _NEW_TOPIC_ANSWER_CHARS:
        return None
    kind = writing_request_kind(asked)
    if kind not in _KIND_FENCE:
        return None
    cleaned = collapse_ws(text)
    if (
        not cleaned
        or len(cleaned.split()) > _ANSWER_MAX_WORDS
        or writing_request_kind(cleaned) is not None
        or is_lightweight_chat_turn(cleaned)
        or _DROPS_DRAFT.match(cleaned)
        or _ASKS_BACK.match(cleaned)
    ):
        return None
    return _KIND_FENCE[kind]


def _draft_in_history(prior_messages: Sequence[tuple[str, str]]) -> tuple[str, bool] | None:
    for role, content in reversed(prior_messages[-_FOLLOWUP_LOOKBACK:]):
        if role == "assistant":
            fences = draft_langs(content)
            if fences:
                return fences[-1], True
            if len(content) > _NEW_TOPIC_ANSWER_CHARS:
                return None
        elif role == "user":
            asked = writing_request_kind(content)
            if asked in _KIND_FENCE:
                return _KIND_FENCE[asked], False
            if len(content.split()) >= _NEW_TOPIC_WORDS:
                return None
    return None
