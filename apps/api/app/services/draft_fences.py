"""The send-ready drafts a reply can hold: ```email, ```message, ```linkedin, …

Chat, reminders and settings ask the same question about the reply before a
turn. After a draft, "add that I'll be late tomorrow at 9", "less groveling"
or "put it in Amharic" edits the draft; it is not a reminder, a settings
change or a new topic.
"""

from __future__ import annotations

from app.services.md_fence_scan import iter_fences

# The draft fences the mobile fence registry draws as copy cards.
DRAFT_LANGS = frozenset(
    {
        "email", "message", "sms", "reply", "copy", "twitter", "tweet", "x", "linkedin",
        "facebook", "fb", "instagram", "insta", "ig", "tiktok", "threads", "caption", "social",
    }
)  # fmt: skip


def draft_langs(text: str | None) -> list[str]:
    """The languages of the reply's draft fences, in order."""
    if not text:
        return []
    return [fence.lang for fence in iter_fences(text) if fence.lang in DRAFT_LANGS]


def has_draft(text: str | None) -> bool:
    """True when the reply holds a send-ready draft."""
    return bool(draft_langs(text))
