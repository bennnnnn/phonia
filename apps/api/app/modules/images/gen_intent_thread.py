"""Image-generation intent across a thread: follow-ups, "that car", and revisions.

``gen_intent`` reads one message; this reads it with the user's earlier lines
or a picture just made: "Dog" then "Image", a picture of "that car", "make it
blue" after a generated picture. ``intent.py`` combines both.

Matching is linear token scans — no ``\\s+`` / ``.+`` regex on user chat text
(CodeQL ``py/polynomial-redos``).
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from app.modules.images.gen_intent import (
    USER_MESSAGE_PREFIX,
    clean_prompt,
    extract_image_gen_prompt,
    has_non_image_draw,
    has_non_image_subject,
    is_image_gen_generate_now,
    join_subject,
    names_a_diagram,
    strip_polite,
)
from app.modules.images.gen_intent_words import (
    DEICTIC_SUBJECTS,
    IMAGE_NOUNS,
    NON_REVISION,
    NOT_REVISION_STARTERS,
    NOUN_ONLY_FILLER,
    REACTION_PHRASES,
    REACTION_WORDS,
    SHOW_NON_IMAGE_WORDS,
    SHOW_REVISION_TARGETS,
    VERBS_DRAW,
    VERBS_IMAGE,
)
from app.services.text_normalize import fold_token

_MODALS = frozenset({"can", "can't", "cant", "cannot", "could", "couldn't", "will", "won't"})
_YOU = frozenset({"you", "u"})


def _strip_doubt(tokens: list[str]) -> list[str]:
    """ "U can't create an image" / "can't you make a picture": the ask, without who."""
    pair = {fold_token(token).replace("\u2019", "'") for token in tokens[:2]}
    return tokens[2:] if len(pair) == 2 and pair & _YOU and pair & _MODALS else tokens


def is_image_noun_only_message(text: str) -> bool:
    """True for a bare image ask with no subject: ``Image``, ``a pic``, ``create an image``."""
    if is_image_gen_generate_now(text):
        return False
    tokens = _strip_doubt(strip_polite(text.strip().rstrip(".!?").split()))
    if tokens and (tokens[0].lower() in VERBS_IMAGE or tokens[0].lower() in VERBS_DRAW):
        tokens = tokens[1:]
        if tokens and tokens[0].lower() == "me":
            tokens = tokens[1:]
    kept = [tok for tok in tokens if tok.lower() not in NOUN_ONLY_FILLER]
    if not kept:
        return False
    return all(tok.lower() in IMAGE_NOUNS for tok in kept)


def could_be_image_thread_followup(text: str) -> bool:
    """True if this line might complete a prior 'dog' + 'image' thread.

    Used to skip the Neon recent-message lookup when the text cannot be a
    follow-up even with prior subject context.
    """
    return is_image_noun_only_message(text) or is_image_gen_generate_now(text)


def _thread_subject_from_user(text: str) -> str | None:
    """Prior user line usable as a generate subject (short concrete noun)."""
    trimmed = text.strip()
    if not trimmed or len(trimmed) > 80 or "?" in trimmed:
        return None
    if is_image_noun_only_message(trimmed) or is_image_gen_generate_now(trimmed):
        return None
    existing = extract_image_gen_prompt(trimmed)
    if existing:
        return existing
    words = trimmed.split()
    if not words or len(words) > 6:
        return None
    first = words[0].lower().rstrip(".!,")
    if first in NOT_REVISION_STARTERS:
        return None
    if has_non_image_subject(trimmed) or has_non_image_draw(trimmed):
        return None
    cleaned = clean_prompt(trimmed)
    if not cleaned or cleaned.lower() in NON_REVISION:
        return None
    return cleaned


def prior_user_contents_for_image_gen(messages: list[Any], current: str) -> list[str]:
    """Oldest-first user bodies, excluding the in-flight current line if present."""
    current_stripped = current.strip()
    out: list[str] = []
    for row in messages:
        role = getattr(row, "role", None)
        content = getattr(row, "content", None)
        if role is None and isinstance(row, dict):
            role = row.get("role")
            content = row.get("content")
        if role != "user" or not isinstance(content, str):
            continue
        out.append(content)
    if out and out[-1].strip() == current_stripped:
        out.pop()
    return out


def is_deictic_subject(subject: str) -> bool:
    """``that car`` / ``it``: a subject named earlier in the chat."""
    first = fold_token(subject.split()[0]) if subject.split() else ""
    return first in DEICTIC_SUBJECTS


def _resolve_deictic_subject(direct: str, prior_user_contents: list[str]) -> str:
    if not is_deictic_subject(direct):
        return direct
    for prior in reversed(prior_user_contents):
        subject = extract_image_gen_prompt(prior)
        if subject and not is_deictic_subject(subject):
            return subject
    return direct


def extract_image_gen_prompt_from_thread(
    text: str,
    prior_user_contents: list[str],
) -> str | None:
    """Same as ``extract_image_gen_prompt``, plus 'Dog' then 'Image' follow-ups.

    A picture of "that car" uses the previous concrete subject.
    """
    direct = extract_image_gen_prompt(text)
    if direct:
        return _resolve_deictic_subject(direct, prior_user_contents)
    if is_image_noun_only_message(text):
        for prior in reversed(prior_user_contents):
            subject = _thread_subject_from_user(prior)
            if subject:
                return subject
        return None
    if not is_image_gen_generate_now(text):
        return None
    return _subject_from_active_image_exchange(prior_user_contents)


def _subject_from_active_image_exchange(prior_user_contents: list[str]) -> str | None:
    """Confirm ("do it") only against the current image exchange, not any older ask."""
    skipped_noun_only = False
    for prior in reversed(prior_user_contents):
        if is_image_gen_generate_now(prior):
            continue
        if is_image_noun_only_message(prior):
            skipped_noun_only = True
            continue
        explicit = extract_image_gen_prompt(prior)
        if explicit:
            return explicit
        if skipped_noun_only:
            return _thread_subject_from_user(prior)
        return None
    return None


def _is_reaction(text: str) -> bool:
    collapsed = " ".join(text.strip().lower().split()).rstrip(".!?").strip()
    if collapsed.startswith("please "):
        collapsed = collapsed[len("please ") :].strip()
    if not collapsed:
        return False
    if collapsed in REACTION_PHRASES:
        return True
    return collapsed.split()[0] in REACTION_WORDS


def _has_edit_lead_in(tokens: list[str]) -> bool:
    i = 0
    n = len(tokens)
    if i < n and tokens[i].lower() == "please":
        i += 1
    if i + 1 < n and tokens[i].lower() == "make" and tokens[i + 1].lower() in {"it", "them"}:
        return True
    if i + 1 < n and tokens[i].lower() == "change" and tokens[i + 1].lower() in {"it", "them"}:
        return True
    return i < n and tokens[i].lower() in {"now", "again", "instead", "try"}


_SHOW_NON_IMAGE_SYMBOLS = "+-\u00d7\u00f7*/=^"


def _is_show_image_revision(tokens: list[str]) -> bool:
    if len(tokens) < 3 or tokens[0].lower() != "show":
        return False
    if any(symbol in tok for tok in tokens for symbol in _SHOW_NON_IMAGE_SYMBOLS):
        return False
    words = [fold_token(tok) for tok in tokens]
    if any(word in SHOW_NON_IMAGE_WORDS for word in words):
        return False
    if any(a == "long" and b == "division" for a, b in pairwise(words)):
        return False
    return words[1] in SHOW_REVISION_TARGETS


def subject_from_image_gen_user_message(content: str) -> str | None:
    """Subject from a prior image-gen user bubble (legacy prefix or natural wording)."""
    trimmed = content.strip()
    if trimmed.lower().startswith(USER_MESSAGE_PREFIX.lower()):
        return clean_prompt(trimmed[len(USER_MESSAGE_PREFIX) :])
    return extract_image_gen_prompt(trimmed)


def is_image_only_assistant_content(content: str) -> bool:
    """True when the assistant bubble is only an ``[Image: …]`` marker."""
    has_image = False
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("[Image:") and s.endswith("]") and len(s) > len("[Image:]"):
            has_image = True
            continue
        return False
    return has_image


def _strip_revision_lead_in(tokens: list[str]) -> list[str]:
    """Drop ``make it`` / ``change them to`` / ``now`` style lead-ins (linear)."""
    i = 0
    n = len(tokens)
    if i < n and tokens[i].lower() == "please":
        i += 1
    if (
        i + 1 < n
        and tokens[i].lower() == "make"
        and tokens[i + 1].lower()
        in {
            "it",
            "them",
        }
    ):
        return tokens[i + 2 :]
    if (
        i + 1 < n
        and tokens[i].lower() == "change"
        and tokens[i + 1].lower()
        in {
            "it",
            "them",
        }
    ):
        j = i + 2
        if j < n and tokens[j].lower() == "to":
            j += 1
        return tokens[j:]
    if i < n and tokens[i].lower() in {"now", "again", "instead", "try"}:
        return tokens[i + 1 :]
    return tokens[i:]


def extract_image_revision_prompt(
    text: str,
    *,
    last_assistant_is_image_only: bool,
    previous_subject: str | None,
) -> str | None:
    """Short follow-up after an image-only reply → new generate prompt."""
    if not last_assistant_is_image_only or not previous_subject:
        return None
    trimmed = text.strip()
    if not trimmed or len(trimmed) > 120:
        return None
    if not _has_edit_lead_in(trimmed.split()) and _is_reaction(trimmed):
        return None

    tokens = _strip_revision_lead_in(trimmed.split())
    if not tokens or len(tokens) > 8:
        return None
    if "?" in trimmed:
        return None
    first = tokens[0].lower().rstrip(".!,")
    if first in NOT_REVISION_STARTERS and not _is_show_image_revision(tokens):
        return None
    revision = join_subject(tokens)
    if not revision:
        return None
    if has_non_image_subject(revision) or names_a_diagram(revision):
        return None
    cleaned = clean_prompt(revision)
    if not cleaned:
        return None
    if cleaned.lower() in NON_REVISION:
        return None
    return f"{previous_subject}, {cleaned}"


def could_be_image_revision(text: str) -> bool:
    """True if this text could revise a prior image-only reply.

    Used to skip the Neon recent-message lookup when the text cannot be a
    revision even if the last assistant was image-only (greetings, thanks).
    """
    return (
        extract_image_revision_prompt(
            text,
            last_assistant_is_image_only=True,
            previous_subject="x",
        )
        is not None
    )


def image_gen_revision_context(
    messages: list[Any],
) -> tuple[bool, str | None]:
    """Walk newest→oldest for image-gen context used by revision intercept."""
    last_assistant_is_image_only = False
    previous_subject: str | None = None
    for row in reversed(messages):
        role = getattr(row, "role", None)
        content = getattr(row, "content", None)
        if role is None and isinstance(row, dict):
            role = row.get("role")
            content = row.get("content")
        if not isinstance(content, str):
            content = ""
        if not last_assistant_is_image_only and role == "assistant":
            model = getattr(row, "model", None)
            if model is None and isinstance(row, dict):
                model = row.get("model")
            # Reference-photo lookup is image-only content but must not be
            # treated as an AI-image revision target.
            if model == "image-search-model":
                break
            last_assistant_is_image_only = is_image_only_assistant_content(content)
            if not last_assistant_is_image_only:
                break
            continue
        if last_assistant_is_image_only and role == "user":
            previous_subject = subject_from_image_gen_user_message(content) or "the provided image"
            break
    return last_assistant_is_image_only, previous_subject
