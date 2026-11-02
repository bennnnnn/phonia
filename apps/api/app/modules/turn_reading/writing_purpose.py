"""Whether a draft request already says what the draft is for.

"Write me an email" says nothing yet, so the reply asks one question;
"email my boss about PTO" has its purpose and is drafted now.
"""

import re

from app.modules.turn_reading.writing_kind import PASTED_TEXT, writing_request_kind
from app.modules.turn_reading.writing_locales import is_bare_locale_draft, locale_draft_kind
from app.services.text_normalize import collapse_ws

_WRITING_PURPOSE_MARKERS = (
    " about ",
    " regarding ",
    " saying ",
    " that says ",
    " to say ",
    " letting ",
    " because ",
    " asking ",
    " subject",
    " i will ",
    " i'll ",
    " i'm ",
    " i am ",
    " pto",
    " running late",
    " be late",
    " follow-up",
    " follow up",
    " apology",
    " thank",
    " requesting ",
    " request for ",
    " inviting ",
    " invite ",
    " announcing ",
    " announce ",
    " comparing ",
    " covering ",
    " explaining ",
    " promoting ",
    " celebrating ",
    " sharing ",
    " birthday",
    " congratulat",
    " vacation",
    " time off",
    " meeting",
    " reschedul",
    " cancell",
    " checking in",
    " check-in",
    " update",
    " news",
    # The kind of email or message is its purpose.
    " resignation",
    " resign",
    " quit",
    " complaint",
    " complain",
    " reminder",
    " remind",
    " invitation",
    " welcome",
    " introduc",
    " farewell",
    " goodbye",
    " condolence",
    " sympathy",
    " refund",
    " inquiry",
    " enquiry",
    " recommendation",
    " reference",
    " sick",
    " sorry",
    " wishing",
    " get well",
    " good luck",
    " congrats",
    " happy ",
    " anniversary",
    " graduation",
    " wedding",
    " opening",
    " launch",
    " sale",
    " hiring",
    " job",
)

# What a post or caption shows: "a caption for a beach sunset photo".
_SOCIAL_SUBJECT_MARKERS = (
    " for a ",
    " for an ",
    " for the ",
    " for our ",
    " for my ",
    " of a ",
    " of my ",
)

# "Text my landlord that the heater is broken", "message my wife we're out of
# milk": what to say follows the recipient, with or without "that".
_SAYS_AFTER_RECIPIENT = re.compile(
    r"\bmy [a-z'-]+(?: (?!(?:and|or|in)\b)[a-z'-]+)? "
    r"(?:that \w|(?:the|my|our|his|her|their|i|i'm|i'll|i've|i'd|we|we're|we'll|it|it's|"
    r"he|she|they|there)\b)",
    re.IGNORECASE,
)


def is_underspecified_writing_request(text: str) -> bool:
    """True for a bare sendable draft ask, not a supplied writing task."""
    kind = writing_request_kind(text)
    if kind not in {"email", "message", "social"}:
        return False
    cleaned = f" {collapse_ws(text).lower()} "
    if '"' in cleaned or "\u201c" in cleaned or PASTED_TEXT.search(text):
        return False
    if kind == "social" and any(marker in cleaned for marker in _SOCIAL_SUBJECT_MARKERS):
        return False
    # In another language, a draft named with no more than a recipient is bare.
    if locale_draft_kind(text) is not None:
        return is_bare_locale_draft(text)
    if _SAYS_AFTER_RECIPIENT.search(cleaned):
        return False
    return not any(marker in cleaned for marker in _WRITING_PURPOSE_MARKERS)
