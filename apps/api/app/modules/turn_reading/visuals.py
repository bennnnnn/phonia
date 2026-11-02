"""Whether a message asks for an HTML preview, a picture, or where a place is."""

from __future__ import annotations

import re

_HTML_UI_TURN = re.compile(
    r"(?:"
    r"\b(?:html|css)\b|"
    r"\b(?:web\s+)?ui\b|"
    r"\blanding\s+page\b|"
    r"\blogin\s+(?:page|screen|form)\b|"
    r"\bdashboard\b|"
    r"\binteractive\s+mockup\b|"
    r"```html\b"
    r")",
    re.IGNORECASE,
)


_HTML_IMAGE_ASK = re.compile(
    r"\b(?:draw|create|generate|make)\s+(?:me\s+)?(?:an?\s+)?(?:image|picture|photo|png)\b",
    re.IGNORECASE,
)


def is_html_ui_question(text: str) -> bool:
    """True when the user asked for a web UI / page mockup, not a generated image."""
    cleaned = text.strip()
    if not cleaned or _HTML_IMAGE_ASK.search(cleaned):
        return False
    return bool(_HTML_UI_TURN.search(cleaned))


_IMAGE_GEN_MENTION_WORDS = (
    "image",
    "images",
    "picture",
    "pictures",
    "pic",
    "pics",
    "photo",
    "photos",
    "illustration",
    "illustrations",
    "artwork",
    "artworks",
    "portrait",
    "portraits",
    "midjourney",
    "craiyon",
)


def _has_whole_word(haystack_lower: str, word: str) -> bool:
    start = 0
    n = len(word)
    while True:
        idx = haystack_lower.find(word, start)
        if idx < 0:
            return False
        before = haystack_lower[idx - 1] if idx > 0 else " "
        after = haystack_lower[idx + n] if idx + n < len(haystack_lower) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        start = idx + n


def is_image_generation_mention(text: str) -> bool:
    """True when the user turn is about a picture / generator (linear scan)."""
    lower = text.lower()
    if not lower:
        return False
    if "dall-e" in lower or "dalle" in lower or "stable diffusion" in lower:
        return True
    for word in _IMAGE_GEN_MENTION_WORDS:
        if _has_whole_word(lower, word):
            return True
    return False


# "where is kenya" / "what country is Timbuktu in" / "show me where Nepal is".
_WHERE_IS = re.compile(
    r"^\s*(?:(?:hey|so|ok(?:ay)?|um+|and)[,\s]+)?(?:please\s+)?"
    r"(?:(?:can|could)\s+you\s+(?:please\s+)?(?:tell|show)\s+me\s+|(?:tell|show)\s+me\s+"
    r"|do\s+you\s+know\s+|i\s+(?:wonder|want\s+to\s+know)\s+)?"
    r"(?:where(?:\s+exactly)?(?:['\u2019]?s|\s+is|\s+are)(?:\s+exactly)?\s+(?P<a>.+?)"
    r"(?:\s+(?:located|situated|exactly|on\s+(?:the|a)\s+map|in\s+the\s+world))?"
    r"|where\s+(?P<b>.+?)\s+(?:is|are)(?:\s+(?:located|on\s+(?:the|a)\s+map))?"
    r"|where\s+in\s+the\s+world\s+(?:is|are)\s+(?P<c>.+?)"
    r"|what\s+(?:country|continent|state|province|region|part\s+of\s+the\s+world)"
    r"\s+(?:is|are)\s+(?P<d>.+?)\s+in)"
    r"\s*[?.!]*\s*$",
    re.IGNORECASE,
)


# Things people lose or look for that are not on a map.
_NOT_A_PLACE = re.compile(
    r"^(?:my|your|our|his|her|their|its|it|this|that|these|those|he|she|they|we|i|you|me|him"
    r"|them|(?:every|some|any)(?:one|body|thing|where)|home|here|there|now"
    r"|the\s+(?:rest|end|answer|catch|logic))\b"
    r"|\b(?:near(?:est|by)?|closest|around\s+here|from\s+here|error|mistake|bug|typo|problem"
    r"|issue|setting|button|option|menu|file|folder|function|variable|code|password"
    r"|phone|key|wallet|remote|order|package|parcel|delivery|money|refund|chat|message"
    r"|download|toilet|bathroom|restroom)s?\b",
    re.IGNORECASE,
)


_MAX_PLACE_WORDS = 6


def where_is_place(text: str) -> str | None:
    """The place in "where is kenya" when the turn asks where somewhere is, else None."""
    match = _WHERE_IS.match(text or "")
    if match is None:
        return None
    place = next(group for group in match.group("a", "b", "c", "d") if group).strip()
    if not place or len(place.split()) > _MAX_PLACE_WORDS or _NOT_A_PLACE.search(place):
        return None
    return place
