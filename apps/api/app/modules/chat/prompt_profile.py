"""Who the user is, as the system prompt states it.

The profile block (or the first name alone on a slim turn) and the user's own
instructions. Account email is shared only when the turn needs it.
"""

from __future__ import annotations

import re

from app.models.orm import User
from app.modules.account import profile as profile_service
from app.modules.turn_reading.writing_kind import is_email_or_message_request
from app.services import prompt_safety

# Account email is PII — only inject when the turn clearly needs it.
_PROFILE_EMAIL_ASK = re.compile(
    r"\b("
    r"what(?:'s| is) my (?:e-?mail|email address)|"
    r"remind me (?:of |what )?my (?:e-?mail|email)|"
    r"(?:tell|show|give) me my (?:e-?mail|email address)"
    r")\b",
    re.IGNORECASE,
)


def should_include_profile_email(query_text: str | None) -> bool:
    """True when the turn needs the account email (an ask or a draft)."""
    cleaned = (query_text or "").strip()
    if not cleaned:
        return False
    if _PROFILE_EMAIL_ASK.search(cleaned):
        return True
    return is_email_or_message_request(cleaned)


# The user sends the drafts Recall writes, so the sign-off is their own name.
_SIGN_DRAFTS_WITH = (
    "Sign emails and messages the user will send as {first}. Never write [Your Name] "
    "or another placeholder."
)
_NO_NAME_TO_SIGN = (
    "With no name on file, end emails and messages on the closing word (Love, Best,) "
    "with no name line. Never write [Your Name] or another placeholder."
)


def format_user_profile_block(
    user: User,
    *,
    location_override: str | None = None,
    include_email: bool = False,
) -> str:
    """Basic identity — injected into every chat prompt."""
    lines = [
        "User profile (internal — from their account; do not quote email or location "
        "unless they explicitly ask for those details):"
    ]
    if user.name and user.name.strip():
        lines.append(f"- Name: {user.name.strip()}")
    if include_email and user.email and user.email.strip():
        lines.append(f"- Email: {user.email.strip()}")
    plan = (user.plan or "free").strip().lower()
    if plan not in {"free", "pro"}:
        plan = "free"
    lines.append(f"- Plan: {plan}")
    if user.age is not None:
        lines.append(f"- Age: {user.age}")
    if user.country and user.country.strip():
        lines.append(f"- Country: {user.country.strip()}")
    if user.job and user.job.strip():
        lines.append(f"- Job: {user.job.strip()}")
    location = location_override or profile_service.user_location_label(user)
    if location:
        lines.append(f"- Location: {location}")
    lines.append(
        "Share profile fields only when the user asks for that specific field — never recite "
        "email or location in a general 'who am I' answer. Do not say their name is missing "
        "from memory if it is listed here."
    )
    if user.name and user.name.strip():
        lines.append(_SIGN_DRAFTS_WITH.format(first=user.name.strip().split()[0]))
    else:
        lines.append(_NO_NAME_TO_SIGN)
    return "\n".join(lines)


def format_user_name_only_block(user: User) -> str:
    """First name only: sign their drafts, answer 'who am I', share no other profile field."""
    name = (user.name or "").strip()
    if not name:
        return (
            "User name is not on file — for a 'who am I' reply, say you don't have their name yet "
            f"without inventing one. {_NO_NAME_TO_SIGN}"
        )
    first = name.split()[0]
    return (
        f"User's first name: {first}. Use it in a 'who am I' reply; share no other profile "
        f"detail. {_SIGN_DRAFTS_WITH.format(first=first)}"
    )


def custom_instructions_block(user: User) -> str | None:
    """The user's own instructions, marked as their preferences; None when they wrote none."""
    return prompt_safety.custom_instructions_block(user.custom_instructions)
