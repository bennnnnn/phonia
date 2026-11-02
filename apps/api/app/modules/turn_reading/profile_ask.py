"""Is the user asking for a detail of their own saved profile ("what's my second language")?

A yes is answered from memory without the model (``turn_prep/instant.py``), so a wrong yes
is a wrong reply: "Who is the principal of my school?" got "I don't have your education
level saved." The profile word has to be the thing asked for, the user's own:

- "what's my education level", "my second langauge", "do you know my school?"
- "which school do I go to", "what grade am I in", "what languages do I speak"
- "where do I live", "where am I from", "where did I study"

Not a profile question: something else at the school ("the principal of my school", "the
rules at my university"), something the school or grade does ("when does my school start",
"my grades dropped"), someone else's ("what grade should my son be in"), or a choice to make
("what language should I learn").
"""

import re

from app.services.text_normalize import collapse_ws

_NOUN = r"(?:education|school|university|college|degree|grades?|languages?|langauges?)"

_PROFILE_FACT_QUESTION = re.compile(
    r"(?:"
    # "what's my education level", "my second langauge", "do you know my school?":
    # the profile word ends the ask.
    rf"\bmy(?:\s+\w+){{0,3}}\s+{_NOUN}(?:\s+(?:level|name|background))?"
    r"(?:\s+(?:again|please|now))?\s*[?.!]*$"
    # "which school do I go to", "what grade am I in", "how many languages do I speak".
    rf"|\b(?:what|which|how many)\s+(?:\w+\s+){{0,2}}{_NOUN}\s+(?:do|did|am|was|have|had)\s+i\b"
    # "I'm in which grade?"
    rf"|\b(?:i am|i'm|im)\s+(?:in|at)\s+(?:what|which)\s+{_NOUN}\b"
    r"|\bwhere am i from\b"
    r"|\bwhere do i live\b"
    r"|\bwhere (?:do|did) i (?:go to (?:school|college|university)|study|attend)\b"
    r")",
    re.IGNORECASE,
)
# Asks about someone or something else: who teaches, when it starts, how to improve, and
# the school as the place of something else ("the principal of my school"). The name of
# the user's school is still theirs ("what's the name of my school?").
_ABOUT_SOMETHING_ELSE = re.compile(
    r"^(?:who|whom|whose|when|why|how(?!\s+many\s+languages))\b"
    rf"|(?<!\bname )\b(?:of|at|in|for|from|to|near|about|with|by)\s+my(?:\s+\w+){{0,2}}\s+{_NOUN}\b",
    re.IGNORECASE,
)
_PROFILE_PUSHBACK = re.compile(
    r"\b(?:(?:u|you) don'?t know|(?:u|you) should know)\b",
    re.IGNORECASE,
)
_TELL_ME = re.compile(r"^(?:(?:u|you) )?tell me[.!?]*$", re.IGNORECASE)
_LANGUAGE_SLOT = re.compile(
    r"^(?:the |my )?(first|second|native|other)(?: one| language| langauge)?[.!?]*$",
    re.IGNORECASE,
)
_LANGUAGE_TOPIC = re.compile(r"\b(?:language|langauge)s?\b", re.IGNORECASE)


_PROFILE_QUESTION_LEAD = re.compile(
    r"^(?:what|what'?s|which|where|do you (?:know|remember)|tell me|guess)\b",
    re.IGNORECASE,
)
# "My second language" is a profile ask; "write an email to the school saying
# my son is sick" or "rewrite my bio: I'm a teacher…" is a writing request.
_PROFILE_PHRASE_WORDS = 8
_PROFILE_QUESTION_WORDS = 14


def is_profile_fact_question(text: str) -> bool:
    """True when they ask for a detail their profile may already hold."""
    cleaned = collapse_ws(text)
    if not cleaned:
        return False
    words = len(cleaned.split())
    asks = _PROFILE_QUESTION_LEAD.match(cleaned) or cleaned.endswith("?")
    if words > _PROFILE_QUESTION_WORDS or (words > _PROFILE_PHRASE_WORDS and not asks):
        return False
    from app.modules.turn_reading.writing_kind import writing_request_kind

    if writing_request_kind(cleaned) is not None:
        return False
    if _ABOUT_SOMETHING_ELSE.search(cleaned):
        return False
    return bool(_PROFILE_FACT_QUESTION.search(cleaned))


def is_profile_recall_pushback(text: str) -> bool:
    """True when they say you should already know, after a profile question."""
    cleaned = collapse_ws(text)
    if not cleaned or len(cleaned) > 48:
        return False
    return bool(_PROFILE_PUSHBACK.search(cleaned) or _TELL_ME.match(cleaned))


def _language_slot_followup(content: str, prior_user_texts: list[str]) -> str | None:
    """'Second' after a language question asks for that language, not a new topic."""
    match = _LANGUAGE_SLOT.match(collapse_ws(content))
    if match is None:
        return None
    slot = match.group(1).lower()
    if slot == "native":
        slot = "first"
    for text in reversed(prior_user_texts):
        if is_profile_recall_pushback(text):
            continue
        if not _LANGUAGE_TOPIC.search(text):
            break
        if slot == "other":
            slot = "first" if re.search(r"\bsecond\b", text, re.IGNORECASE) else "second"
        return f"what is my {slot} language"
    return None


def profile_question_to_answer(content: str, prior_user_texts: list[str]) -> str | None:
    """The profile question this turn is asking, including a later 'you tell me'."""
    if is_profile_fact_question(content):
        return content
    slotted = _language_slot_followup(content, prior_user_texts)
    if slotted:
        return slotted
    if not is_profile_recall_pushback(content):
        return None
    for text in reversed(prior_user_texts):
        if is_profile_fact_question(text):
            return text
        if is_profile_recall_pushback(text):
            continue
        break
    return None
