"""Pure input validators shared by Pydantic schemas (no DB/IO/services)."""

from __future__ import annotations

import re
from uuid import UUID

# ISO 639-1 codes supported by the mobile app (see apps/mobile/lib/i18n/languages.ts).
LOCALE_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "tr": "Turkish",
    "am": "Amharic",
}

BORING_CHAT_TITLES = frozenset(
    {
        "new chat",
        "untitled",
        "chat",
        "conversation",
        "new conversation",
    }
)


def normalize_display_name(raw: str | None) -> str | None:
    """Trim, collapse whitespace, and enforce length for user-visible names."""
    if raw is None:
        return None
    name = " ".join(raw.strip().split())
    if not name or len(name) > 80:
        return None
    return name


_AVATAR_PATH_PREFIX = "/attachments/"
_AVATAR_PATH_SUFFIX = "/file"


def normalize_avatar_url(raw: str | None) -> str | None:
    """Accept only our uploaded-photo path ``/attachments/<uuid>/file``."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if not text.startswith(_AVATAR_PATH_PREFIX) or not text.endswith(_AVATAR_PATH_SUFFIX):
        raise ValueError("Avatar must be an uploaded photo.")
    inner = text[len(_AVATAR_PATH_PREFIX) : -len(_AVATAR_PATH_SUFFIX)]
    try:
        attachment_id = UUID(inner)
    except ValueError as exc:
        raise ValueError("Avatar must be an uploaded photo.") from exc
    if str(attachment_id) != inner.lower():
        raise ValueError("Avatar must be an uploaded photo.")
    return f"{_AVATAR_PATH_PREFIX}{attachment_id}{_AVATAR_PATH_SUFFIX}"


def normalize_locale_code(locale: str | None) -> str:
    if not locale:
        return "en"
    return locale.split("-")[0].lower()


# Straight + curly quotes models often wrap titles with.
_TITLE_QUOTES = "\"'" + "\u201c\u201d\u2018\u2019"
# Trailing sentence punctuation that can sit outside the closing quote.
_TITLE_TRAIL_PUNCT = ".!?,;:"
# One-shot unwrap: leading quotes, or trailing quotes + optional punct.
_TITLE_WRAP_RE = re.compile(
    rf"^[{re.escape(_TITLE_QUOTES)}]+|[{re.escape(_TITLE_QUOTES)}]+[{re.escape(_TITLE_TRAIL_PUNCT)}]*$"
)
# Markdown emphasis the title model occasionally emits ("**Document Summaries**",
# once "**D**ocument** Summaries"). Bold runs never belong in a title; single
# `*`/`_` pairs are stripped only at word boundaries so "x*2" and snake_case
# survive.
_TITLE_BOLD_RE = re.compile(r"\*\*|__")
_TITLE_EM_STAR_RE = re.compile(r"(?<!\w)\*([^*\n]+)\*(?!\w)")
_TITLE_EM_UNDER_RE = re.compile(r"(?<!\w)_([^_\n]+)_(?!\w)")


def _strip_title_emphasis(title: str) -> str:
    title = _TITLE_BOLD_RE.sub("", title)
    prev = None
    while prev != title:
        prev = title
        title = _TITLE_EM_STAR_RE.sub(r"\1", title)
        title = _TITLE_EM_UNDER_RE.sub(r"\1", title)
    return title


def unwrap_chat_title(raw: str) -> str:
    """Strip wrapping quotes/punct/emphasis until stable (fixes '"My Trip Plan".')."""
    title = raw.strip()
    while True:
        prev = title
        title = _strip_title_emphasis(title)
        title = _TITLE_WRAP_RE.sub("", title).strip()
        title = title.rstrip(_TITLE_TRAIL_PUNCT).strip()
        title = title.strip(_TITLE_QUOTES).strip()
        if title == prev:
            return title


def normalize_chat_title(raw: str | None) -> str | None:
    if not raw:
        return None
    title = unwrap_chat_title(raw)
    if not title:
        return None
    if title.lower() in BORING_CHAT_TITLES:
        return None
    if len(title) < 3 or len(title) > 80:
        return None
    return title


def normalize_stored_chat_title(raw: str | None) -> str | None:
    """Display a saved title, including short or generic user-chosen labels."""
    title = unwrap_chat_title(raw or "")
    return title if title and len(title) <= 80 else None


def claim_is_true(value: object) -> bool:
    """True only for an explicit, unambiguous true claim in an identity token.

    Apple sends boolean claims as the strings "true"/"false"; Google sends bools
    (some intermediaries pass the string form). A missing claim or anything else
    (incl. "false", 0, None) is false.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False
