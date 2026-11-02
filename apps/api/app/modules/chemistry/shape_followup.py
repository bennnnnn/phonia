"""A line that only asks to see the molecules of the shape question before it.

Live failure (2026-10-25): after "Why is water bent tho, co2 isnt" the student wrote "Can u show
me both", which a photo search for "both" took, then "lol no the molecules", which got ASCII
art in a code box and a broken CO2 drawing. The server draws each molecule of a verified shape
answer (``chem_scene``), so a line that only asks to see them gets that answer again.

Every word of the line must come from one closed set: a verb that shows ("show", "display",
"let me see", "look like"), what is shown ("both", "them", "each of them", "the molecules",
"the models", "the drawings"), and fillers ("lol", "no", "can u", "pls", "then"). Review
(2026-10-25): phrase by phrase, "show me both of them", "show me what they look like" and
"show us both" fell through to a photo search. "draw" and "sketch" are not show verbs here: the
composer sends "draw both" to image generation before a chat turn exists. A word for a
real photo ("photo", "pic", "image", "real") is never this line: "show me a photo of both" stays
a photo. The noun alone counts too ("lol no the molecules"). The shape question is the latest
earlier user line that is not such a line itself; any other line in between declines, so "show
me both" after a crocodile and an alligator is not chemistry's.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from typing import Any

from app.modules.chemistry.extractors.shapes import shape_question
from app.services.problem_followup import message_role_content

# A show line is short; anything longer asks something else.
_MAX_LINE = 200
_WORD = re.compile(r"[a-z0-9']+")
# "draw" and "sketch" are left to image generation: the composer reads "draw both" as a picture
# before any chat turn, and the composer's reading is the chat turn's (``images/intent``).
_SHOW_VERBS = frozenset({"show", "display", "visualize", "visualise"})
_PICTURE_NOUNS = frozenset(
    {
        "molecule",
        "molecules",
        "shape",
        "shapes",
        "structure",
        "structures",
        "drawing",
        "drawings",
        "diagram",
        "diagrams",
        "model",
        "models",
        "picture",
        "pictures",
    }
)
_SHOWN = frozenset({"both", "them", "they", "those", "these", "it", "each", "all", "ones"})
_FILLERS = frozenset(
    {
        "can",
        "could",
        "would",
        "will",
        "u",
        "you",
        "pls",
        "plz",
        "please",
        "me",
        "us",
        "i",
        "want",
        "wanna",
        "need",
        "to",
        "let",
        "lemme",
        "just",
        "now",
        "then",
        "again",
        "too",
        "also",
        "of",
        "the",
        "a",
        "an",
        "what",
        "like",
        "at",
        "do",
        "does",
        "in",
        "3d",
        "for",
        "ok",
        "okay",
        "lol",
        "lmao",
        "haha",
        "no",
        "nah",
        "nope",
        "yes",
        "yeah",
        "yep",
        "so",
        "and",
        "but",
        "mean",
        "actually",
        "instead",
        "thanks",
        "thx",
        "side",
        "by",
        "together",
        "look",
        "see",
    }
)
# A real photo is a photo: never redrawn.
_PHOTO_WORDS = frozenset(
    {"photo", "photos", "photograph", "photographs", "pic", "pics", "image", "images", "real"}
    | {"irl", "actual", "video", "videos"}
)
# Earlier user lines read for the shape question; show lines between are passed.
_MAX_LINES = 4
# What a shape question says, read before the grammar is asked (a cheap first look).
_SHAPE_CUE = re.compile(
    r"\b(?:shapes?|geometr|bent|linear|polar|bond\s+angle|tetrahedral|pyramidal|planar|vsepr|"
    r"angular)",
    re.IGNORECASE,
)


def _shows(words: list[str]) -> bool:
    """A verb that shows: "show", "draw", "let me see", "can i see", "look like"."""
    for index, word in enumerate(words):
        before = words[index - 1] if index else ""
        after = words[index + 1] if index + 1 < len(words) else ""
        if word in _SHOW_VERBS:
            return True
        if word == "see" and (
            before in {"me", "to", "wanna"}
            or words[max(index - 2, 0)]
            in {
                "can",
                "could",
            }
        ):
            return True
        if word == "look" and after in {"like", "at"}:
            return True
    return False


def is_show_line(text: str | None) -> bool:
    """True when every word of the line asks to see the molecules, and none a photo."""
    if not text or len(text) > _MAX_LINE:
        return False
    words = _WORD.findall(text.lower())
    vocabulary = _SHOW_VERBS | _PICTURE_NOUNS | _SHOWN | _FILLERS
    if not words or any(word in _PHOTO_WORDS or word not in vocabulary for word in words):
        return False
    shown = _SHOWN | _PICTURE_NOUNS | {"me", "us"}
    if _shows(words):
        return any(word in shown for word in words)
    # The noun alone: "lol no the molecules".
    return any(word in _PICTURE_NOUNS - {"picture", "pictures"} for word in words) and not any(
        word in {"look", "see", "want", "need"} for word in words
    )


def _user_lines(recent: Sequence[Any]) -> Iterator[str]:
    seen = 0
    for message in reversed(recent):
        role, content = message_role_content(message)
        if role != "user" or not content or not content.strip():
            continue
        yield content
        seen += 1
        if seen == _MAX_LINES:
            return


def last_question_line(recent: Sequence[Any]) -> str | None:
    """The latest earlier user line that is not itself a show line."""
    for earlier in _user_lines(recent):
        if not is_show_line(earlier):
            return earlier
    return None


def could_ask_a_shape(line: str | None) -> bool:
    """A cheap first look: short, and with a word a shape question says."""
    return line is not None and len(line) <= _MAX_LINE and _SHAPE_CUE.search(line) is not None


def shape_followup_problem(line: str, recent: Sequence[Any]) -> str | None:
    """The shape question whose molecules this line asks to see, or None."""
    if not is_show_line(line):
        return None
    earlier = last_question_line(recent)
    if earlier is None or not could_ask_a_shape(earlier):
        return None
    return earlier if shape_question(earlier) is not None else None
