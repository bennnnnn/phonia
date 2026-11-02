"""Asking for the lesson the last reply just taught: point to it, never teach it again.

"Teach me American sayings" opened with Lesson 1 and its practice question; "Very
interesting. Lets start with 1" then got Lesson 1 word for word (live, 2026-10-25), and
on the free model it read the 1 as the quiz answer and went on to Lesson 2. The turn
hint (``lesson_again_hint``) asks for one short pointer; the finalize pass holds it: a
reply that writes a lesson or a quiz anyway becomes that pointer.

The ask is read by a positive grammar: "let's start with 1", "start with lesson 1", "go
back to lesson 2", "show me lesson 2", after at most a short reaction ("Very
interesting."). A bare "1", "start at 1" or "I think it's 1" is an answer to the quiz,
never this, and so is anything after a gap (the recap path), a teach-me line (a new
lesson) or a regenerated reply (the lesson above is the one being redone). The grammar
is English, so a message it reads is English, and so is the pointer.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.modules.turn_reading.lesson_flow import active_lesson_step, lesson_after_gap, lesson_titles
from app.modules.turn_reading.turn import teaching_of
from app.services.md_fence_scan import iter_fences
from app.services.text_normalize import straighten_apostrophes

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

_FIRST = {"1": 1, "one": 1, "first": 1, "the first": 1, "the first one": 1}
_NUMBER = r"(\d{1,2}|one|(?:the\s+)?first(?:\s+one)?)"
_LEAD = r"(?:(?:ok(?:ay)?|so|great|cool|nice|alright|sure|yes|yeah|hmm+)\W+)*"
_WE = r"(?:let'?s|lets|let\s+us|can\s+we|could\s+we|shall\s+we|i\s+want\s+to|i'?d\s+like\s+to)"
_ASK = re.compile(
    rf"^\W*{_LEAD}(?:please\s+)?"
    rf"(?:{_WE}\s+(?:start|begin)\s+(?:with|from|at)\s+(?:lesson\s+|number\s+|#)?(?P<n1>{_NUMBER})"
    rf"|(?:start|begin)\s+(?:with|from|at)\s+lesson\s+(?P<n2>{_NUMBER})"
    rf"|(?:{_WE}\s+)?(?:go\s+(?:back\s+)?to|show\s+me|do|give\s+me)\s+lesson\s+(?P<n3>{_NUMBER}))"
    r"(?:\s+please)?\W*$",
    re.IGNORECASE,
)
_SENTENCES = re.compile(r"(?<=[.!?])\s+")
# A reaction before the ask ("Very interesting."): a few words, no number or option.
_WORD = r"[^\W\d_]{2,}(?:'[^\W\d_]+)?"
_REACTION = re.compile(rf"^\W*(?:{_WORD}\W+){{0,2}}{_WORD}\W*$")


def asked_lesson(text: str | None) -> int | None:
    """The lesson number the message asks to start or go to, or None."""
    sentences = _SENTENCES.split(straighten_apostrophes(text or "").strip())
    if not sentences[-1] or not all(_REACTION.match(s) for s in sentences[:-1]):
        return None
    found = _ASK.match(sentences[-1])
    if found is None:
        return None
    number = found.group("n1") or found.group("n2") or found.group("n3") or ""
    words = " ".join(number.lower().split())
    return _FIRST.get(words) or (int(words) if words.isdigit() else None)


def lesson_again(text: str | None, recent: list[Any] | None) -> int | None:
    """The lesson the user asks for when it is the one the last reply taught, or None.

    Not after a gap (that turn recaps), and not on a teach-me line (a new lesson)."""
    current = active_lesson_step(recent)
    if current is None or asked_lesson(text) != current or teaching_of(text or ""):
        return None
    return None if lesson_after_gap(recent) else current


def lesson_again_hint(number: int) -> str:
    """The turn hint when the user asks for the lesson they are on."""
    return (
        f"The learner asked for Lesson {number}, which your previous reply already taught; "
        "it ends with its practice question. Reply in one or two short sentences: they are "
        f"on Lesson {number}, it is just above, try its practice question, and 'next' brings "
        f"Lesson {number + 1}. Do not grade anything. Write no lesson, no heading and no quiz."
    )


def pointer(number: int) -> str:
    return (
        f"You're on Lesson {number} now: it's just above. Try its practice question, or say "
        f'"next" for Lesson {number + 1}.'
    )


def keep_to_lesson_again_pass(state: FinalizeState) -> str:
    """The finalize pass: a reply that teaches or quizzes again becomes the pointer."""
    # A regenerated reply is still last in ``recent_messages``: it is the one being redone.
    if state.server_text or getattr(state.ctx, "regenerate_backup", None) is not None:
        return state.text
    number = lesson_again(state.ctx.user_message_content, state.ctx.recent_messages)
    if number is None:
        return state.text
    teaches = bool(lesson_titles(state.text)) or any(
        fence.lang == "quiz" for fence in iter_fences(state.text)
    )
    return pointer(number) if teaches else state.text
