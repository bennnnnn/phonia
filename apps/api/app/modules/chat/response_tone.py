"""Preset response tones and emoji use — mapped into chat system prompts."""

import re

from app.models.schemas.common import EmojiUse, ResponseTone

DEFAULT_RESPONSE_TONE: ResponseTone = "casual"

TONE_HINTS: dict[str, str] = {
    "funny": (
        "Tone: FUNNY and playful. Use light humor and wit when it fits — stay "
        "helpful, accurate, and never mock the user. "
        "Exception: a one-line arithmetic identity (3+0, 4!, 2+2) stays one line — "
        "no bit, no personification, no coffee-break bit. A maths, physics or "
        "chemistry answer gets no joke at all, and never one about the learner."
    ),
    "professional": (
        "Tone: PROFESSIONAL. Polished, clear, and respectful. Avoid slang unless the user "
        "uses it first."
    ),
    # "Like texting" read as lowercase: "h₂o", "10°c", "thursday", "boyle's law" (2026-10-24).
    "casual": (
        "Tone: CASUAL and friendly. Conversational and relaxed — like texting a smart friend, "
        "in word choice only: write with normal capitals (sentences, names, days, months) and "
        "never lowercase a chemical formula (H₂O), a unit (°C, K) or a variable (P, V)."
    ),
    "soft": (
        "Tone: SOFT and gentle. Warm, supportive phrasing. Avoid harsh, blunt, or "
        "judgmental wording."
    ),
}


def tone_hint(tone: str | None) -> str:
    key = tone if tone in TONE_HINTS else DEFAULT_RESPONSE_TONE
    return TONE_HINTS[key]


# How many emoji a reply uses (Settings → Personalization). The tone never decides it.
DEFAULT_EMOJI_USE: EmojiUse = "some"

# Where an emoji never goes, whatever the setting: it would break what is read there.
_EMOJI_NEVER = (
    "Never in a number, maths, code, a fenced card, a worked maths, physics or chemistry "
    "solution, an answer to a school exercise, a draft the user will send, or a reply "
    "about something painful."
)

# A saved "prefers replies without emojis" outranked "more" (2026-10-24): the setting decides.
_EMOJI_SETTING = "This is the user's Emoji setting; a saved memory never changes it."
EMOJI_HINTS: dict[str, str] = {
    "off": "Emoji: none. No emoji in a reply, lessons included, unless the user writes one. "
    + _EMOJI_SETTING,
    "some": (
        "Emoji: a few, to help the reader scan. A fitting emoji may lead a heading or a list "
        "item's bold label (### 🧠 Memory, 1. 💧 **Drink water** — …), at most one each, and "
        "nowhere else: none in a sentence, an opening line or a closing question; a short "
        "plain answer gets none. " + _EMOJI_NEVER + " " + _EMOJI_SETTING
    ),
    "more": (
        "Emoji: plenty, the user likes them. A fitting emoji leads every heading and every "
        "list item's label, ✅ and ❌ may mark yes and no in a comparison, and a short "
        "friendly line may carry one. " + _EMOJI_NEVER + " " + _EMOJI_SETTING
    ),
}


def emoji_hint(level: str | None) -> str:
    return EMOJI_HINTS[level if level in EMOJI_HINTS else DEFAULT_EMOJI_USE]


# The Emoji line sits at the top of the prompt, far from the message, and lost: at "Lots", a
# list of tips came back with no emoji in most replies (2026-10-29), and a fact saved before
# memory left settings alone ("User prefers replies in English and without emojis") pulls
# the same way. Like the language note, this one goes beside the message (message_notes;
# not in a lesson, outline or clarify card, which place their own). "Lots" gets it on every
# other turn (the user asked for them); "A few" only when a loaded memory states an emoji
# preference; "off" needs none (emoji_placement removes them).

# A line of memory that states an emoji preference ("User prefers no emojis"), not one that
# only names them ("Building an emoji picker app"): that one is a fact, not out of date.
_EMOJI_LINE = re.compile(r"^.*\bemoj(?:i|is)\b.*$", re.IGNORECASE | re.MULTILINE)
_PREFERS = re.compile(
    r"\b(?:prefer\w*|lik(?:e|es|ed)|lov(?:e|es|ed)|hat(?:e|es|ed)|want\w*|avoid\w*|without|no|"
    r"fewer|more|lots|plenty|less)\b",
    re.IGNORECASE,
)


def _emoji_preference_in(memory_block: str) -> bool:
    return any(_PREFERS.search(line) for line in _EMOJI_LINE.findall(memory_block))


def emoji_note(level: str | None, memory_block: str) -> str | None:
    """The Emoji setting, said beside the message, when the line at the top may not hold.

    The note carries where emoji never go, so being nearest the message it cannot outrank
    them; a lesson keeps its own rule (one in the opening line)."""
    level = level if level in EMOJI_HINTS else DEFAULT_EMOJI_USE
    competing = _emoji_preference_in(memory_block)
    if level == "more":
        note = (
            "Emoji in this reply: plenty, as the user's Emoji setting says. A fitting emoji "
            "leads every heading and every list item's label (1. 💧 **Drink water** — …). "
            + _EMOJI_NEVER
            + " A lesson keeps its own emoji rule."
        )
    elif level == "some" and competing:
        note = (
            "Emoji in this reply: a few, as the user's Emoji setting says (the Emoji line above)."
        )
    else:
        return None
    if competing:
        note += " A saved memory about emoji is out of date and does not change it."
    return note
