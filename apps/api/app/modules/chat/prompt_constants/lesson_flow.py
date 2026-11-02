"""Where a lesson stands: the lesson the last reply taught, or the outline it asked from.

A teach-me reply is either Lesson N (title, sections, a practice quiz) or, for a
whole subject, an outline that ends asking where to start. The next turn goes
on from either one.
"""

from __future__ import annotations

from app.modules.chat.prompt_constants.teaching import _LESSON_OPENING, _LESSON_SHAPE


def lesson_continue_hint(number: int, *, after_gap: bool = False) -> str:
    """The turn after a lesson: grade the practice if answered, then the next lesson.

    ``after_gap``: the lesson was a day or more ago, so the next one opens by
    recalling it (retrieval before new material).
    """
    nxt = number + 1
    recap = (
        f"\nLESSON {number} WAS OVER A DAY AGO. Unless the latest message answers its practice "
        "question, the reply must start, before the new lesson's title, with `**Quick "
        f"recap**`: two short lines on Lesson {number}'s key idea, then one warm-up ```quiz "
        f'on it (label "Warm-up"). Only then `### Lesson {nxt}: ...` (the warm-up is not a '
        f"lesson, so the number is {nxt}) on what Lesson {number}'s preview promised."
        if after_gap
        else ""
    )
    return (
        f"A lesson is in progress. The learner has ALREADY SEEN Lesson {number}, which ended "
        "with a practice ```quiz (they can check it in the app) and a preview of the next "
        f"lesson. Do not repeat Lesson {number}. Read the latest message first:\n"
        '- An answer to the practice question: if right, start with "Correct! 🎉" and say why '
        'in one sentence; if wrong or partial, start with "Not quite", fix that one '
        "misunderstanding in 1-3 sentences with a fresh tiny example, and do not ask them to "
        f"try again. Then teach Lesson {nxt}.\n"
        f"- 'next', 'ok', 'got it', 'continue' or similar: teach Lesson {nxt}.\n"
        "- Confusion ('I don't get it', 'why?', 'another example'): stay on the same idea, "
        f"explain it a different way with a new analogy and example under the same "
        f"`### Lesson {number}: ...` title, and end with a fresh ```quiz.\n"
        "- A question about the lesson: answer it first, then continue.\n"
        "- Accidental or unclear input: do not grade it; give the practice answer in one "
        f"sentence and teach Lesson {nxt}.\n"
        "- A request to skip, stop, change topic, get everything at once, a summary or a "
        "cheat sheet: do that instead of the next lesson.\n"
        f"Lesson {nxt} covers what the preview promised, without a greeting or an outline, "
        "in the same shape (the app's ```quiz, ```array and ```steps cards included):\n"
        + _LESSON_SHAPE
        + recap
    )


OUTLINE_PICK_HINT = (
    "Your previous reply outlined a subject the user wants to learn and asked where to "
    "start. Read the latest message:\n"
    "- A number, a topic, 'start', their level or their goal: teach Lesson 1 on the topic it "
    "picks (the first topic for 'start' or a beginner, the first one they don't know for a "
    "level, the one that leads to their goal) without repeating the outline, in this "
    "shape:\n" + _LESSON_OPENING + _LESSON_SHAPE + "\n"
    "- Anything else (another question, a change of mind): answer that instead."
)


def lesson_turn_hint(
    lesson: int | None, *, outline_pick: bool, after_gap: bool = False
) -> str | None:
    """How this turn goes on: the next lesson, Lesson 1 from the outline, or neither."""
    if lesson:
        return lesson_continue_hint(lesson, after_gap=after_gap)
    return OUTLINE_PICK_HINT if outline_pick else None
