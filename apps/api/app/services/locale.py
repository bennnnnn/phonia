"""User locale → human-readable language hints for LLM system prompts."""

from __future__ import annotations

from app.core.validation import LOCALE_NAMES as LOCALE_NAMES
from app.core.validation import normalize_locale_code as normalize_locale_code


def locale_display_name(locale: str | None) -> str:
    code = normalize_locale_code(locale)
    return LOCALE_NAMES.get(code, locale or "English")


# An English app got no language line, so a saved "replies in Spanish" and then the Spanish
# reply above it decided: "Teach me how to improve recall" was answered in Spanish, and the
# English messages after it too (2026-10-24).
REPLY_LANGUAGE_ORDER = (
    "If their custom instructions name a reply language, use it. Otherwise write in the "
    "language of their latest message; a message with no language of its own (a number, "
    "'ok', code, a photo) keeps the language of their message before it. A saved memory, "
    "an earlier chat or an earlier reply in another language never sets it."
)


def locale_system_hint(locale: str | None) -> str:
    """The reply language: their instructions, then their message, then the app's."""
    code = normalize_locale_code(locale)
    name = locale_display_name(code)
    return (
        f"The user's app language is {name} (locale code: {code}): write replies in {name} "
        f"unless they write in another language or ask in this conversation for one. "
        f"When the user changes app language, follow it at once. " + REPLY_LANGUAGE_ORDER
    )
