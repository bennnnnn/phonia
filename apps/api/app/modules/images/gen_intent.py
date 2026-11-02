"""Detect image-generation intent in one message: the word rules ``intent.py`` reads.

``gen_intent_thread`` reads a message with the thread before it (follow-ups,
"that car", revisions) and builds on the token helpers here.

The server is their only reader; ``docs/fixtures/image_intent_cases.json`` holds
the cases (``tests/modules/images/test_intent_contract.py``).

Matching is linear token scans — no ``\\s+`` / ``.+`` regex on user chat text
(CodeQL ``py/polynomial-redos``).
"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import TYPE_CHECKING

from app.modules.images.gen_intent_local import extract_other_language_prompt
from app.modules.images.gen_intent_second import SECOND_ASKS, asks_separately
from app.modules.images.gen_intent_words import (
    ARTICLES,
    CODEISH_WORDS,
    DIAGRAM_WORDS,
    GENERATE_NOW_EXACT,
    MAKE_IDIOM_FILLER,
    MAKE_NOT_A_PICTURE,
    NON_IMAGE_DRAW_WORDS,
    NON_IMAGE_WORDS,
    NOT_REVISION_STARTERS,
    NOUN_MESSAGE_FILE_WORDS,
    POSSESSIVES,
    REVISION_PRONOUNS,
    SUBJECTLESS_FILLER,
    VERBS_DRAW,
    VERBS_IMAGE,
)
from app.modules.images.gen_intent_words import IMAGE_NOUNS as IMAGE_NOUNS  # chat reads it here
from app.services.diagram_kinds import names_diagram_kind, names_idea_curve
from app.services.text_normalize import fold_token

if TYPE_CHECKING:
    from app.services.subjects.dispatch import SubjectName

USER_MESSAGE_PREFIX = "Generate image: "
_PURPOSE_COLON = re.compile(
    r"^(?:please\s+)?(?:generate|create|make|draw|design)\s+(?:me\s+)?(?:an?\s+)?"
    r"(?:image|picture|photo|pic|illustration|drawing|poster|graphic)\s+for\s+[^:\n]{1,80}:"
    r"\s*(?P<subject>\S[^\n]*)$",
    re.IGNORECASE,
)


def strip_polite(tokens: list[str]) -> list[str]:
    i = 0
    n = len(tokens)
    if i < n and tokens[i].lower() == "please":
        i += 1
    if i + 1 < n and tokens[i].lower() == "can" and tokens[i + 1].lower() == "you":
        i += 2
    return tokens[i:]


def join_subject(parts: list[str]) -> str:
    return " ".join(parts).strip()


def clean_prompt(raw: str) -> str | None:
    prompt = raw.strip().rstrip(".!?").strip()
    if not prompt or len(prompt) < 2:
        return None
    if any(fold_token(w) in CODEISH_WORDS for w in prompt.split()):
        return None
    return prompt


def has_non_image_subject(subject: str, *, drawn: bool = False) -> bool:
    """A subject that is not a picture: a task, notes, code. With a ``drawn`` verb
    (draw, paint, illustrate), what follows "for" is what the picture is for: "draw me a
    cute cartoon skeleton for my notes" drew nothing, as if the notes were the subject."""
    words = [fold_token(word) for word in subject.split()]
    if drawn and "for" in words[1:]:
        words = words[: words.index("for", 1)]
    for i, key in enumerate(words):
        if key in NON_IMAGE_WORDS and not _names_what_the_art_is_for(words, i):
            return True
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if (key, nxt.removesuffix("s")) in _NON_IMAGE_PAIRS:
            return True
    return False


# Two words naming something written: "a pull request", "a cover letter", "a random number".
_NON_IMAGE_PAIRS = frozenset({("pull", "request"), ("cover", "letter"), ("random", "number")})


# Pictures made for something: "a poster for my event", "an app logo".
_ART_FOR_NOUNS = frozenset(
    {
        "logo",
        "logos",
        "icon",
        "icons",
        "poster",
        "posters",
        "banner",
        "banners",
        "sticker",
        "stickers",
        "mascot",
        "mascots",
        "flyer",
        "flyers",
        "thumbnail",
        "thumbnails",
        "wallpaper",
        "wallpapers",
    }
)
# "A logo for my site in html" asks for markup, not a picture.
_MARKUP_WORDS = frozenset({"html", "css", "javascript", "typescript"})


def _names_what_the_art_is_for(words: list[str], i: int) -> bool:
    """``app`` in "an app logo" or "a logo for my app": what the picture is for, not the ask."""
    if any(word in _MARKUP_WORDS for word in words):
        return False
    if i + 1 < len(words) and words[i + 1] in _ART_FOR_NOUNS:
        return True
    before = words[:i]
    if "for" not in before:
        return False
    purpose = len(before) - 1 - before[::-1].index("for")
    # "A cover image for my presentation": a picture noun heads the request too.
    return any(word in _ART_FOR_NOUNS or word in IMAGE_NOUNS for word in words[:purpose])


def has_non_image_draw(subject: str) -> bool:
    words = [fold_token(word) for word in subject.split()]
    joined = " ".join(words)
    # "Paint a picture with words of a morning in Addis" asks for prose.
    if "sketch of the idea" in joined or "picture with words" in joined:
        return True
    # "A cute cartoon atom for our chemistry club poster" is art, not a diagram.
    if any(word in _ART_WORDS for word in words):
        return False
    return names_a_diagram(subject) or any(word in NON_IMAGE_DRAW_WORDS for word in words)


def names_a_diagram(subject: str) -> bool:
    """A diagram the app draws itself ("a decision tree", "a mind map", "a flowchart"):
    never an AI picture, whose labels come out garbled, and never an edit of the last one."""
    words = [fold_token(word) for word in subject.split()]
    if any(word in _ART_WORDS for word in words):
        return False
    return (
        names_diagram_kind(subject)
        or names_idea_curve(subject)
        or any(word in DIAGRAM_WORDS for word in words)
    )


_ART_WORDS = frozenset(
    {
        "cartoon",
        "poster",
        "sticker",
        "logo",
        "mascot",
        "illustration",
        "watercolor",
        "avatar",
        "cute",
    }
)


def _names_no_subject(parts: list[str]) -> bool:
    """``the image`` / ``just a pic of`` — only fillers and image nouns, no subject."""
    return all(
        fold_token(tok) in IMAGE_NOUNS or fold_token(tok) in SUBJECTLESS_FILLER for tok in parts
    )


_MAX_IMAGE_MODIFIERS = 3


def _match_verb_then_image(tokens: list[str]) -> str | None:
    """create/generate … image/pic … of? SUBJECT

    A few words may describe the picture first (``create a realistic photo of
    a dog``); they stay in the prompt, so the subject must follow ``of``.
    """
    if len(tokens) < 3:
        return None
    if tokens[0].lower() not in VERBS_IMAGE:
        return None
    i = 1
    if i < len(tokens) and tokens[i].lower() == "me":
        i += 1
    if i < len(tokens) and tokens[i].lower() in ARTICLES:
        i += 1
    start = i
    while (
        i < len(tokens)
        and i - start < _MAX_IMAGE_MODIFIERS
        and tokens[i].lower() not in IMAGE_NOUNS
    ):
        i += 1
    if i >= len(tokens) or tokens[i].lower() not in IMAGE_NOUNS:
        return None
    if i > start:
        rest = tokens[i + 2 :]
        if rest and rest[0].lower() in ARTICLES:
            rest = rest[1:]
        if not rest or tokens[i + 1].lower() != "of":
            return None
        i = start
    else:
        i += 1
        if i < len(tokens) and tokens[i].lower() == "of":
            i += 1
    if i >= len(tokens):
        return None
    subject = join_subject(tokens[i:])
    if has_non_image_subject(subject) or has_non_image_draw(subject):
        return None
    return clean_prompt(subject)


def _match_verb_subject_image(tokens: list[str]) -> str | None:
    """create/generate … SUBJECT image/pic/photo"""
    if len(tokens) < 3:
        return None
    if tokens[0].lower() not in VERBS_IMAGE:
        return None
    if tokens[-1].lower() not in IMAGE_NOUNS:
        return None
    i = 1
    if i < len(tokens) - 1 and tokens[i].lower() == "me":
        i += 1
    if i < len(tokens) - 1 and tokens[i].lower() in ARTICLES:
        i += 1
    subject_parts = tokens[i:-1]
    if not subject_parts or _names_no_subject(subject_parts):
        return None
    subject = join_subject(subject_parts)
    if has_non_image_subject(subject) or has_non_image_draw(subject):
        return None
    return clean_prompt(subject)


def _match_draw_me(tokens: list[str]) -> str | None:
    """draw/paint/illustrate me [a/an] SUBJECT"""
    if len(tokens) < 3:
        return None
    if tokens[0].lower() not in VERBS_DRAW:
        return None
    if tokens[1].lower() != "me":
        return None
    i = 2
    if i < len(tokens) and tokens[i].lower() in ARTICLES:
        i += 1
    if i >= len(tokens):
        return None
    subject = join_subject(tokens[i:])
    if has_non_image_subject(subject, drawn=True) or has_non_image_draw(subject):
        return None
    return clean_prompt(subject)


# "Draw up a contract", "draw on my experience", "draw conclusions from the data":
# with one of these next, "draw" writes, uses or infers something rather than draws it.
_DRAW_NOT_A_PICTURE = frozenset(
    {
        "up",
        "on",
        "upon",
        "from",
        "near",
        "nearer",
        "closer",
        "back",
        "away",
        "together",
        "conclusions",
        "inferences",
        "boundaries",
        "attention",
        "inspiration",
        "lots",
        "straws",
    }
)


# The most words "create …" / "draw …" may name, within an 80-character message.
_LONG_SUBJECT_WORDS = 12


def _asks_again(parts: list[str]) -> bool:
    """A second request in the subject: "… and also explain …", "… and tell me …"."""
    words = [word for word in map(fold_token, parts) if word != "also"]
    return any(word in {"and", "then"} and nxt in SECOND_ASKS for word, nxt in pairwise(words))


def _make_is_not_a_picture(subject: str) -> bool:
    """ "Make money", "make a decision about moving": the idiom's noun leads, and no picture
    word follows it ("make a living room illustration" is still a picture)."""
    words = [fold_token(word) for word in subject.split()]
    words = [word for word in words if word and word not in MAKE_IDIOM_FILLER]
    return bool(words) and words[0] in MAKE_NOT_A_PICTURE and not IMAGE_NOUNS & set(words)


def _match_short_create(tokens: list[str]) -> str | None:
    """Short ``draw a dog`` or ``create a cat`` — the whole message is the subject.

    Chat asks such as ``make your own example`` still fail ``has_non_image_subject``.
    ``make money`` is not a picture; ``make a cat photo`` is matched earlier.
    """
    if len(tokens) < 2:
        return None
    verb = tokens[0].lower()
    if verb not in VERBS_DRAW and verb not in VERBS_IMAGE:
        return None
    if verb == "draw" and fold_token(tokens[1]) in _DRAW_NOT_A_PICTURE:
        return None
    i = 1
    if i < len(tokens) and tokens[i].lower() == "me":
        i += 1
    if i < len(tokens) and tokens[i].lower() in ARTICLES:
        i += 1
    subject_parts = tokens[i:]
    # "Create a walking poor man on the streets of Addis Ababa" is nine words; "make"
    # with a long object is more often a task ("make a decision about moving …").
    if not subject_parts or len(subject_parts) > (8 if verb == "make" else _LONG_SUBJECT_WORDS):
        return None
    if subject_parts[0].lower() in REVISION_PRONOUNS:
        return None
    # "create an image" names no subject; the thread may supply one. "Draw a cat and also
    # explain black holes" asks twice: the plan draws the cat beside the answer.
    if _names_no_subject(subject_parts) or _asks_again(subject_parts):
        return None
    subject = join_subject(subject_parts)
    if verb == "make" and _make_is_not_a_picture(subject):
        return None
    # "Make your answers shorter" / "make my code faster" changes something the
    # user already has; "make my profile picture" still names a picture.
    if (
        verb == "make"
        and subject_parts[0].lower() in POSSESSIVES
        and not any(part.lower() in IMAGE_NOUNS for part in subject_parts)
    ):
        return None
    drawn = verb in VERBS_DRAW
    if has_non_image_subject(subject, drawn=drawn) or has_non_image_draw(subject):
        return None
    return clean_prompt(subject)


def _match_image_noun_message(tokens: list[str]) -> str | None:
    """Short colloquial ask: ``cat pic`` / ``a sunset photo`` / ``photo of a cat``.

    The image noun must close the message, or open it before ``of``. A noun in
    the middle (``best photo editing apps``, ``picture this``) is ordinary chat,
    and so is a question or a possessive (``how to take a good photo``).
    """
    if len(tokens) < 2 or len(tokens) > 16:
        return None
    folded = [fold_token(tok) for tok in tokens]
    if folded[-1] in IMAGE_NOUNS:
        parts = tokens[:-1]
    else:
        i = 1 if folded[0] in ARTICLES else 0
        if i + 1 >= len(tokens) or folded[i] not in IMAGE_NOUNS or folded[i + 1] != "of":
            return None
        parts = tokens[i + 2 :]
    if parts and fold_token(parts[0]) in ARTICLES:
        parts = parts[1:]
    if not parts or _names_no_subject(parts):
        return None
    first = fold_token(parts[0])
    if (
        first in POSSESSIVES
        or first in NOT_REVISION_STARTERS
        or first in IMAGE_NOUNS
        # "U can't create an image": who makes it, not what it shows.
        or any(fold_token(part) in VERBS_IMAGE | VERBS_DRAW for part in parts)
    ):
        return None
    subject = join_subject(parts)
    if any(fold_token(w) in NOUN_MESSAGE_FILE_WORDS for w in parts):
        return None
    if has_non_image_subject(subject) or has_non_image_draw(subject):
        return None
    return clean_prompt(subject)


def extract_image_gen_prompt(text: str) -> str | None:
    """Return the image subject if ``text`` is a clear image-gen ask, else None."""
    from app.services.subject_scan import is_scanner_camera_prompt

    trimmed = text.strip()
    if not trimmed or len(trimmed) > 500:
        return None
    # Scanner captions contain "image" and are often ≤80 chars, which the
    # short image-noun heuristic would steal as a generate-image ask.
    if is_scanner_camera_prompt(trimmed):
        return None

    if trimmed.lower().startswith(USER_MESSAGE_PREFIX.lower()):
        return clean_prompt(trimmed[len(USER_MESSAGE_PREFIX) :])
    # "Generate an image for my coffee shop's post: a jebena pouring coffee" —
    # the picture is what follows the colon.
    purpose = _PURPOSE_COLON.match(trimmed)
    if purpose is not None:
        return clean_prompt(purpose.group("subject"))

    tokens = strip_polite(trimmed.split())
    if not tokens:
        return None

    # "Draw me a cat and also explain black holes" asks twice: the plan draws the cat and
    # answers the rest, so no reading here takes the whole line.
    draws_me = len(tokens) > 2 and tokens[0].lower() in VERBS_DRAW and tokens[1].lower() == "me"
    if draws_me and asks_separately(trimmed):
        return None

    matched = _match_verb_then_image(tokens)
    if matched:
        return matched

    matched = _match_verb_subject_image(tokens)
    if matched:
        return matched

    matched = _match_draw_me(tokens)
    if matched:
        return matched

    # Short create/draw only when the whole message is short (same as before).
    if len(trimmed) <= 80:
        matched = _match_short_create(tokens)
        if matched:
            return matched
        matched = _match_image_noun_message(tokens)
        if matched:
            return matched

    # "Zeichne mir eine Katze", "нарисуй мне кошку": draw-me requests in other languages.
    return extract_other_language_prompt(trimmed)


def stem_subject(text: str, *, chemistry_enabled: bool = True) -> SubjectName | None:
    """The maths, physics or chemistry subject that owns this turn instead of image generation.

    "draw ethanol" is a structure and "A lens has focal length 15 cm. Where's the
    image?" is optics; the text rules above would read both as picture requests.
    Art stays art: "a cute cartoon atom for our chemistry club poster" is a picture.
    """
    from app.services.subjects.dispatch import detect_subject

    if any(fold_token(word) in _ART_WORDS for word in text.split()):
        return None
    return detect_subject(text, chemistry_enabled=chemistry_enabled)


def stem_subject_claims(text: str, *, chemistry_enabled: bool = True) -> bool:
    """True when a maths, physics or chemistry subject owns this turn (``stem_subject``)."""
    return stem_subject(text, chemistry_enabled=chemistry_enabled) is not None


def is_image_gen_generate_now(text: str) -> bool:
    """True when this line is 'do it' / 'that works' / 'u pick' after a scene."""
    collapsed = " ".join(text.strip().lower().split()).rstrip(".!?").strip()
    if not collapsed or len(collapsed) > 40:
        return False
    if collapsed in GENERATE_NOW_EXACT:
        return True
    padded = f" {collapsed} "
    return " do it " in padded or " u do it " in padded or " you do it " in padded
