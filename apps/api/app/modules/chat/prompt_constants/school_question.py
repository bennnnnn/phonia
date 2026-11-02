"""A school exercise, said beside the message: the textbook's answer, at its level.

A Class 8 physical science book's exercises (2026-10-30) got answers a student could not
hand in: "That's a riddle dressed as a question", a multiple-choice answer that changed
its mind and blamed the textbook, electroplating aluminium sent to molten cryolite at
1000 °C, a definition answered from a search that cited a YouTube comment, and offers of
more at the end. The note nearest the message is the one a small model keeps to.

A Class 9 book in every subject (2026-10-30) showed the first reader was that book's
phrases: it knew 10 of 129 exercises. An exercise is now read from the shapes every
textbook prints, whatever the subject:

- options to choose from: a stem, then (a) to (d) or (i) to (iv), on their own lines, or
  short, or after "which of the following" / "choose";
- an assertion and its reason, a blank to fill, or two or more labelled parts;
- an exercise's order: "Differentiate between", "Identify", "Justify", "Arrange the
  following", "Calculate", "Give reasons", "Fill in the blanks";
- a scenario about a student, a class, a farmer or a researcher, then a question;
- a closing order ("…? Explain."), an assessment code ("(AS1)"), a textbook's phrase.

Never from words anyone uses ("Explain decorators", "Define success.", "Plan a trip
covering a) Rome b) …", "Calculate my BMI", a Markdown checklist's "[ ]"): a message that
is anyone's own matter (``question_kinds.anyones``) is no exercise, whatever its shape.
Any other question about the world gets the lighter factual note.
"""

from __future__ import annotations

from app.modules.turn_reading.question_kinds import (
    is_factual_question,
)
from app.modules.turn_reading.school_question import ASSERTION, is_school_exercise, option_choice

# A worked answer that states its result first wrote "The ratio is 1 : 5" over working
# that found 4 : 5, and "0.054 s" over a box of 0.015 s (2026-10-30); told to work first
# beside "open with the answer", it opened "The ratio is 2 : 5". A calculation's opening
# is its working.
WORK_FIRST = (
    "A calculation is the exception to answering first: it opens with its working (what "
    "is given, the formula, the substitution) and states its result once, at the end; "
    "never write a number before you have worked it out, and never think aloud (no "
    "'actually', 'wait' or 'let me recheck')."
)
# Told "stay at that level" and "no specialist detail", a Class 10 book's "Which signals
# are disrupted by a spinal cord injury?" got spinal tracts and T1-L2 outflow, and "the
# function of receptors" myasthenia gravis (2026-10-30): a depth the model reads from the
# question alone needs its edge named.
TEXTBOOK_DEPTH = (
    "Go only as deep as a school textbook does: use the terms the question uses or a "
    "textbook would, and no clinical, research or university detail (named pathways, "
    "receptors, diseases, molecular mechanisms, bonding theory) unless the question asks "
    "for it; no side claim you are unsure of."
)
# A factual question may be an adult's ("How do mRNA vaccines work?"): its depth follows its
# own words, and only a question in a school book's words is held to a school book's.
MATCHED_DEPTH = (
    "Go as deep as the question's own words: a question worded like a school book's gets a "
    "school book's answer, with no clinical, research or university detail (named pathways, "
    "receptors, diseases, molecular mechanisms) it did not ask for; one in specialist words "
    "may get a specialist's. No side claim you are unsure of."
)
SCHOOL_QUESTION_NOTE = (
    "This message is a school exercise. Answer it as the textbook expects, for the "
    "student who asked, at the level the question is written, from what the textbook "
    "teaches: open with the answer itself in plain words, using "
    "the textbook's terms, then a short reason or two to four everyday examples. "
    + WORK_FIRST
    + " "
    + TEXTBOOK_DEPTH
    + " No history or regional trivia it did not ask for. Take the question as written: "
    "never call it a trick or a riddle, never dispute its wording, its options or the "
    "textbook, and never ask "
    "where it came from. Answer every part it asks, in order. End when the answer is "
    "complete, with no offer of more."
)
_CHOICE_NOTE = (
    " It asks you to choose: name the one correct option, its label and words, first, "
    "then one or two lines on why; never change the option partway, name two, or say "
    "none is correct."
)
FACTUAL_QUESTION_NOTE = (
    "This is a factual question. Give the standard answer a good textbook gives, first, "
    "in plain words at the level the question is asked, then a short reason or a few "
    "examples. " + WORK_FIRST + " " + MATCHED_DEPTH + " Take the question as written: "
    "never open by disputing it, correcting its wording or calling it a trick, and keep to "
    "what it asks. End when the answer is complete, with no offer of more."
)


def school_question_hint(query: str) -> str | None:
    """The note for a school exercise, or None."""
    if is_school_exercise(query):
        text = query.strip()
        chooses = option_choice(text) or ASSERTION.search(text) is not None
        return SCHOOL_QUESTION_NOTE + (_CHOICE_NOTE if chooses else "")
    return None


def question_hint(query: str) -> str | None:
    """The note beside a message: a school exercise's, a factual question's, or None."""
    return school_question_hint(query) or (
        FACTUAL_QUESTION_NOTE if is_factual_question(query) else None
    )
