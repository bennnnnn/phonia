"""Reject profile facts that assign the user a name they never claimed.

A word problem ("Bebe has 2 pens… Cal") is not an introduction. The account
name is a separate field and is not inferred from other people in the chat.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'"})

# Phrases that state who the user is by name.
_IDENTITY_MARKERS = (
    "user's name is ",
    "users name is ",
    "user name is ",
    "user is named ",
)
# Phrases that give the name the user chose to be called. A bare "also goes by" is
# only a nickname on a fact that already names the user, so a pet's nickname is not
# treated as the user's name.
_NICKNAME_MARKERS = (
    "user goes by ",
    "user also goes by ",
)
_BEFORE_MARKERS = (
    " is the user's name",
    " is the users name",
    " is the user name",
)
_BARE_IDENTITY = ("the user is ", "user is ")

# How the user says who they are, and how they ask to be called.
_IDENTITY_PREFIXES = (
    "my name is ",
    "my name's ",
    "i'm ",
    "i am ",
)
_CHOSEN_PREFIXES = (
    "call me ",
    "i go by ",
    "i also go by ",
    "i prefer to be called ",
    "i'd like to be called ",
    "i want to be called ",
)
_CLAIM_PREFIXES = (*_IDENTITY_PREFIXES, *_CHOSEN_PREFIXES)
_PREFIXES_BY_WAY = {
    "identity": _IDENTITY_PREFIXES,
    "named": ("my name is ", "my name's "),
    "chosen": _CHOSEN_PREFIXES,
    "any": _CLAIM_PREFIXES,
}
# "Pretend I'm Sam", "imagine that my name is Sam": a role, not who the user is. The
# word comes at most three words before, with no comma between ("I imagine you are
# busy, but my name is Sam" is an introduction).
_PLAYED = re.compile(
    r"\b(?:pretend(?:ing)?|imagine|suppose|hypothetically|role-?play(?:ing)?|as if|what if"
    r"|let's say)\b(?: +[\w']+){0,3} *$"
)
# "Don't call me Sam" asks for the opposite.
_REFUSALS = ("don't ", "do not ", "never ", "not ", "stop ")

_NOT_A_NAME = frozenset(
    {"the", "a", "an", "my", "not", "unknown", "missing", "none", "user"}
    # "Call me when you're done", "call me back", "call me crazy".
    | {"when", "if", "back", "later", "tomorrow", "tonight", "anytime", "now", "after"}
    | {"before", "once", "again", "maybe", "crazy", "sometime", "please", "at", "on", "in"}
)


def _fold(text: str) -> str:
    return (text or "").translate(_APOSTROPHES).casefold()


def _user_speech(transcript: str) -> str:
    """User lines only. A transcript with no role labels is treated as the user."""
    raw = transcript or ""
    lines = raw.splitlines() or [raw]
    has_role = False
    for line in lines:
        lowered = line.strip().casefold()
        if lowered.startswith("user:") or lowered.startswith("assistant:"):
            has_role = True
            break
    if not has_role:
        return _fold(raw)
    parts: list[str] = []
    in_user = False
    for raw_line in lines:
        line = raw_line.strip()
        lowered = line.casefold()
        if lowered.startswith("assistant:"):
            in_user = False
            continue
        if lowered.startswith("user:"):
            in_user = True
            line = line.split(":", 1)[1].strip()
            if line:
                parts.append(line)
            continue
        if in_user and line:
            parts.append(line)
    return _fold("\n".join(parts))


def _keep(name: str) -> bool:
    return len(name) >= 2 and name not in _NOT_A_NAME


def _token_at(haystack: str, cursor: int) -> tuple[str, int]:
    while cursor < len(haystack) and haystack[cursor] == " ":
        cursor += 1
    end = cursor
    while end < len(haystack) and (haystack[end].isalpha() or haystack[end] in "-'"):
        end += 1
    return haystack[cursor:end].strip("-'"), end


def _names_after(haystack: str, marker: str) -> list[str]:
    found: list[str] = []
    start = 0
    while True:
        index = haystack.find(marker, start)
        if index < 0:
            return found
        name, _end = _token_at(haystack, index + len(marker))
        if _keep(name):
            found.append(name)
        start = index + len(marker)


def _names_before(haystack: str, marker: str) -> list[str]:
    found: list[str] = []
    start = 0
    while True:
        index = haystack.find(marker, start)
        if index < 0:
            return found
        end = index
        while end > 0 and haystack[end - 1] == " ":
            end -= 1
        cursor = end
        while cursor > 0 and (haystack[cursor - 1].isalpha() or haystack[cursor - 1] in "-'"):
            cursor -= 1
        name = haystack[cursor:end].strip("-'")
        if _keep(name):
            found.append(name)
        start = index + len(marker)


def _bare_identity(folded: str) -> list[str]:
    """'The user is Bebe' is a name. 'The user is a teacher' is not."""
    found: list[str] = []
    for marker in _BARE_IDENTITY:
        start = 0
        while True:
            index = folded.find(marker, start)
            if index < 0:
                break
            if marker == "user is " and folded[max(0, index - 4) : index] == "the ":
                start = index + len(marker)
                continue
            name, end = _token_at(folded, index + len(marker))
            if name == "named":
                start = index + len(marker)
                continue
            rest = folded[end:].strip(" .,;:!")
            if _keep(name) and not rest:
                found.append(name)
            start = index + len(marker)
    return found


def _identity_names(folded: str) -> list[str]:
    names: list[str] = []
    for marker in _IDENTITY_MARKERS:
        names.extend(_names_after(folded, marker))
    for marker in _BEFORE_MARKERS:
        names.extend(_names_before(folded, marker))
    names.extend(_bare_identity(folded))
    return names


def _unique(names: list[str]) -> list[str]:
    return list(dict.fromkeys(names))


def assigned_user_names(text: str) -> list[str]:
    """Names this sentence assigns to the user. Empty when it does not."""
    folded = _fold(text)
    if "user" not in folded:
        return []
    names = _identity_names(folded)
    for marker in _NICKNAME_MARKERS:
        names.extend(_names_after(folded, marker))
    if names:
        names.extend(_names_after(folded, "also goes by "))
    return _unique(names)


def _claimed(speech: str, name: str, prefixes: tuple[str, ...] = _CLAIM_PREFIXES) -> bool:
    for prefix in prefixes:
        phrase = prefix + name
        start = 0
        while True:
            index = speech.find(phrase, start)
            if index < 0:
                break
            before_ok = index == 0 or not speech[index - 1].isalnum()
            after = index + len(phrase)
            possessive = after < len(speech) and speech[after] == "'"
            after_ok = after >= len(speech) or not speech[after].isalnum()
            if before_ok and after_ok and not possessive and not _PLAYED.search(speech[:index]):
                return True
            start = index + 1
    return False


def is_unclaimed_user_name(
    text: str,
    transcript: str,
    existing_texts: Iterable[str] = (),
) -> bool:
    """True when a fact gives the user a name their own words did not claim.

    A name already stored as the user's name still counts. A later nickname
    ('I also go by Ben') must not drop the earlier 'User's name is Bini'.
    """
    names = assigned_user_names(text)
    if not names:
        return False
    known: set[str] = set()
    for existing in existing_texts:
        known.update(assigned_user_names(existing))
    return any(name not in known and not user_claimed_name(transcript, name) for name in names)


def user_claimed_name(
    transcript: str, name: str, *, way: Literal["identity", "named", "chosen", "any"] = "any"
) -> bool:
    """The user's own lines give ``name`` as who they are ("I'm Sam", ``identity``; only
    "my name is Sam", ``named``) or as what to call them ("call me Sam", ``chosen``).
    "Don't call me Sam" and "pretend I'm Sam" claim nothing."""
    speech = _user_speech(transcript)
    folded = _fold(name)
    if not _keep(folded) or any(f"{refusal}call me {folded}" in speech for refusal in _REFUSALS):
        return False
    return _claimed(speech, folded, _PREFIXES_BY_WAY[way])
