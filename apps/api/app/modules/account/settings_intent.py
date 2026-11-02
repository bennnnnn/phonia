"""The one setting a chat line changes: the theme ("switch to dark mode").

Every other setting (model, tone, language, memory) is changed by hand in Settings;
no chat line proposes it. Linear token / phrase scans only — no ``\\s+`` / ``.+``
regex on user text (CodeQL ``py/polynomial-redos``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.services.draft_fences import has_draft

SettingsField = Literal["appearance"]

_APPEARANCE_NICKNAMES: dict[str, str] = {
    "dark": "dark",
    "night": "dark",
    "light": "light",
    "day": "light",
    "system": "system",
    # "default" = follow the system theme, the product default. Without
    # this the heuristic misses "switch to default theme" and the user has no
    # way to undo an explicit light/dark choice via chat. ("auto" is NOT
    # aliased here — it collides with the "auto" model alias.)
    "default": "system",
}

_CHANGE_CUES = frozenset(
    {
        "switch",
        "change",
        "set",
        "use",
        "enable",
        "turn",
        "go",
        "put",
        "make",
        "be",
    }
)

_CONTENT_VERBS = frozenset(
    {
        "write",
        "draft",
        "explain",
        "summarize",
        "translate",
        "tell",
        "show",
        "list",
        "create",
        "generate",
        "draw",
        "learn",
        "study",
        "start",
        "how",
    }
)

_SETTINGS_NOUNS = frozenset({"theme", "appearance", "mode", "setting", "settings"})

_PUNCT = frozenset("?!.,;:\"'`")

_MAX_COMMAND_TOKENS = 12

_SHORT_DRAFT_EDIT = 6
_REVISION_REFERENCES = frozenset(
    {"it", "this", "that", "version", "message", "email", "draft", "reply", "text"}
)
_POINTERS = frozenset({"it", "this", "that"})
_ASKING_WORDS = frozenset(
    {"please", "pls", "plz", "want", "prefer", "need", "talk", "speak", "reply", "respond"}
)
_CLAUSE_BREAK = re.compile(r"[,;.!]\s+")
# A letter or message written out in prose: "Dear Tsehay,", "Subject: …", "Hi team,".
_LETTER = re.compile(
    r"(?:\**subject:?\**\s|dear\s|hi\s+\w+,|hello\s+\w+,|hey\s+\w+,)", re.IGNORECASE
)
_SYSTEM_WORDS = frozenset({"system", "phone", "phone's", "device", "device's", "os"})
_QUESTION_OPENERS = frozenset(
    {"is", "are", "was", "were", "does", "do", "did", "which", "what", "whats", "why", "should"}
)
_EXPLICIT_SETTINGS_WORDS = frozenset(
    {"setting", "settings", "default", "app", "recall", "preference", "preferences"}
)


@dataclass(frozen=True, slots=True)
class SettingsChange:
    field: SettingsField
    value: str


def _strip_punct(token: str) -> str:
    start = 0
    end = len(token)
    while start < end and token[start] in _PUNCT:
        start += 1
    while end > start and token[end - 1] in _PUNCT:
        end -= 1
    return token[start:end]


def _tokens(content: str) -> list[str]:
    return [_strip_punct(part).lower() for part in content.split() if _strip_punct(part)]


def _has_content_request(tokens: list[str]) -> bool:
    return any(token in _CONTENT_VERBS for token in tokens)


def _has_change_cue(tokens: list[str]) -> bool:
    return any(token in _CHANGE_CUES for token in tokens)


def _has_settings_noun(tokens: list[str]) -> bool:
    return any(token in _SETTINGS_NOUNS for token in tokens)


# "Change the language of this paragraph to French" or "make the email's tone
# formal" is about a piece of text, not the app's settings; "change my name to
# Claude" is about the user's profile, which no chat line sets.
_CONTENT_TARGETS = frozenset(
    {
        "name",
        "nickname",
        "username",
        "paragraph",
        "paragraphs",
        "sentence",
        "sentences",
        "text",
        "email",
        "message",
        "essay",
        "post",
        "poem",
        "letter",
        "caption",
        "story",
        "article",
        "reply",
        "draft",
        "document",
        "doc",
        "line",
        "lines",
        "word",
        "words",
        "title",
        "bio",
        "speech",
        "lyrics",
        "code",
        "website",
        "site",
        "webpage",
        "slide",
        "slides",
        "resume",
        "cv",
        "tweet",
        "opening",
        "intro",
        "introduction",
        "ending",
        "conclusion",
        "greeting",
        "closing",
        "headline",
        "hook",
    }
)


def _without_possessive(token: str) -> str:
    """ "email's" -> "email"."""
    for suffix in ("'s", "\u2019s"):
        if token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _looks_like_command(tokens: list[str]) -> bool:
    if not tokens or len(tokens) > _MAX_COMMAND_TOKENS:
        return False
    if _has_content_request(tokens):
        return False
    if any(_without_possessive(token) in _CONTENT_TARGETS for token in tokens):
        return False
    if _has_change_cue(tokens) or len(tokens) <= 4:
        return True
    # "The light mode on my phone hurts my eyes" talks about a mode; it asks
    # for nothing. A longer line needs a verb, "please", or "I want".
    return _has_settings_noun(tokens) and bool(_ASKING_WORDS & set(tokens))


def _revises_prior_draft(tokens: list[str], prior_assistant: str | None) -> bool:
    """Keep referential writing edits out of permanent app settings.

    ``Make it less formal`` is a settings command in isolation, but immediately
    after a ``message``/``email`` draft, "it" refers to that artifact. After
    any other reply, "make it funnier" still points at that reply. Explicit
    app/preference wording still opts into a persistent setting change.
    """
    if not (prior_assistant or "").strip():
        return False
    if any(word in _EXPLICIT_SETTINGS_WORDS for word in tokens):
        return False
    if not has_draft(prior_assistant) and not _LETTER.match((prior_assistant or "").lstrip()):
        return not _has_settings_noun(tokens) and any(word in _POINTERS for word in tokens)
    # "Less groveling, more casual" names no "it", yet still edits the draft.
    return len(tokens) <= _SHORT_DRAFT_EDIT or any(word in _REVISION_REFERENCES for word in tokens)


def _asks_a_question(tokens: list[str], *, asked: bool = False) -> bool:
    """ "Is the pro model worth it?" or "dark mode vs light mode?" asks; it changes nothing."""
    return bool(tokens) and (
        tokens[0] in _QUESTION_OPENERS
        or any(word in {"vs", "versus"} for word in tokens)
        # "light mode or dark mode for reading at night?" weighs two; it picks neither.
        or (asked and "or" in tokens)
    )


def _window_has(tokens: list[str], left: str, right: str) -> bool:
    for index, token in enumerate(tokens[:-1]):
        if token == left and tokens[index + 1] == right:
            return True
    return False


def _extract_appearance(tokens: list[str]) -> str | None:
    if _window_has(tokens, "match", "system"):
        return "system"
    # "Make the app theme follow my phone's setting."
    follows = "follow" in tokens or "match" in tokens
    if follows and _SYSTEM_WORDS & set(tokens) and {"theme", "appearance", "mode"} & set(tokens):
        return "system"
    for index, word in enumerate(tokens):
        value = _APPEARANCE_NICKNAMES.get(word)
        if value is None:
            continue
        nxt = tokens[index + 1] if index + 1 < len(tokens) else ""
        prev = tokens[index - 1] if index > 0 else ""
        if nxt in {"mode", "theme", "appearance"} or prev in {"theme", "appearance", "to"}:
            return value
        if word in {"dark", "light"} and (nxt == "" or nxt in _CHANGE_CUES or nxt == "please"):
            if _has_change_cue(tokens) or _has_settings_noun(tokens) or len(tokens) <= 3:
                return value
        if word == "system" and nxt in {"theme", "appearance", "mode"}:
            return "system"
    return None


def extract_settings_changes(
    content: str, *, prior_assistant: str | None = None
) -> list[SettingsChange]:
    """The theme change a chat line asks for, or empty if it asks for none.

    "Switch to dark mode pls, writing in bed and the screen is blinding" says
    the command in its first clause; each clause is read when the whole is not.
    """
    found = _changes_in(content, prior_assistant)
    if found or len(_tokens(content)) <= _MAX_COMMAND_TOKENS // 2:
        return found
    if content.rstrip().endswith("?") or any(
        _without_possessive(token) in _CONTENT_TARGETS for token in _tokens(content)
    ):
        return []
    for clause in _CLAUSE_BREAK.split(content):
        # Only a clause that opens with a verb: "switch to dark mode pls, …".
        words = _tokens(clause)
        if not words or words[0] not in _CHANGE_CUES:
            continue
        found = _changes_in(clause, prior_assistant)
        if found:
            return found
    return []


def _changes_in(content: str, prior_assistant: str | None) -> list[SettingsChange]:
    tokens = _tokens(content)
    asked = content.rstrip().endswith("?")
    if not _looks_like_command(tokens) or _asks_a_question(tokens, asked=asked):
        return []
    if _revises_prior_draft(tokens, prior_assistant):
        return []
    appearance = _extract_appearance(tokens)
    return [] if appearance is None else [SettingsChange("appearance", appearance)]
