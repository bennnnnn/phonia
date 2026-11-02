"""What one turn's message is, read once: the turn's ``TurnReading`` (structure ticket ST-05).

The turn's decisions used to be recomputed where each was used, from whatever text that
caller held. The reading is built once from the pooled read of the message
(``chat.turn_prep.reading.read_turn``) and kept for the turn; callers read its fields.
It holds the plan and whether the message asks to be taught; the subject decision joins
it next, with the reason code the turn's trace line records. (Small talk is the turn's
mode, ``chat.turn_prep.mode``: it reads the window, not only the message.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.core.readings import keep_for_turn, kept_for_turn
from app.modules.turn_reading.plan import TurnPlan
from app.modules.turn_reading.teaching import TeachingReason, is_teaching_request

# Why the plan is what it is: one request, several, or the pool read gave up (the whole
# message as one request, as every turn before plans).
PlanReason = Literal["one_request", "several_requests", "read_declined"]

_KEPT = "turn_reading"


@dataclass(frozen=True)
class TurnReading:
    # The message read, and the setting that reads chemistry in it.
    text: str
    chemistry_enabled: bool
    plan: TurnPlan
    plan_reason: PlanReason
    # Whether the message asks to be taught, and why (``turn_reading.teaching``).
    teaching_reason: TeachingReason
    # The message's subject as the pool read it with the turn's attachment flag and
    # chemistry setting, and the step of the subject order that decided it
    # (``services.subjects.dispatch.read_subject_reason``). ``not_read`` when the pool did not
    # read it, ``read_declined`` when the pool gave up: the subject is then unknown here.
    has_image_attachment: bool = False
    subject: str | None = None
    subject_reason: str = "not_read"
    # The message's requests (``request_units``) that ask about a place or the weather on
    # their own words, each with the subject the pool read in it (None: none, or not read).
    # One a subject does not claim keeps its reader beside the homework (``is_homework``).
    place_requests: tuple[tuple[str, str | None], ...] = ()

    @property
    def teaching(self) -> bool:
        return self.teaching_reason == "teach"

    def knows_subject_of(
        self, text: str, *, has_image_attachment: bool, chemistry_enabled: bool
    ) -> bool:
        """Whether this reading holds the subject of ``text`` read with these flags."""
        return (
            self.subject_reason not in ("not_read", "read_declined")
            and self.text == text
            and self.has_image_attachment == has_image_attachment
            and self.chemistry_enabled == chemistry_enabled
        )

    def reads(self, text: str, *, chemistry_enabled: bool) -> bool:
        """Whether this is the reading of ``text``: a caller holding another text (a part,
        a rewritten line) reads that text itself."""
        return self.text == text and self.chemistry_enabled == chemistry_enabled


def keep_turn_reading(reading: TurnReading) -> None:
    keep_for_turn(_KEPT, reading)


def current_turn_reading() -> TurnReading | None:
    """This turn's reading, or None outside a turn or before its message was read."""
    kept = kept_for_turn(_KEPT)
    return kept if isinstance(kept, TurnReading) else None


_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def request_units(text: str, plan: TurnPlan) -> tuple[str, ...]:
    """The message's requests as one reader judges each: the plan's parts when it splits the
    message, else its sentences ("Will it rain tomorrow? And what's 15% of 80?")."""
    if plan.multi:
        return plan.texts()
    return tuple(part for part in _SENTENCE_BREAK.split(" ".join(text.split())) if part)


def is_homework(text: str) -> bool:
    """Whether ``text`` is the turn's message and homework throughout: the turn's reading
    gives it a subject (physics, maths, chemistry), solved or not, and every request in it that
    asks about a place or the weather on its own words has a subject too. A part of the
    turn's plan that the plan reads as a solve is homework as well: the planner read it with
    its subject and the problem's setup (``turn_prep.intents``), and the search gates read
    each part alone.

    Homework is its subject's question before it is one about the user's place
    (``web_search.weather.is_worked_problem``): "A ball is dropped from a height of 20 m. How
    long does it take to reach the ground?" asks about the ball. "What's the weather like
    today? Also solve 2x + 3 = 7" still asks the forecast. Spacing aside (callers collapse
    it), only the turn's own message is known; any other text, or no turn, is False. Nothing
    is read here: the subject order runs in the pool.
    """
    kept = current_turn_reading()
    if kept is None:
        return False
    if kept.plan.multi and any(
        part.kind == "solve" and _same_line(part.text, text) for part in kept.plan.parts
    ):
        return True
    if kept.subject is None or not _same_line(kept.text, text):
        return False
    return all(subject is not None for _, subject in kept.place_requests)


def _same_line(left: str, right: str) -> bool:
    return left.split() == right.split()


def teaching_of(text: str) -> bool:
    """Whether ``text`` asks to be taught: the turn's own reading when ``text`` is the turn's
    message, else that text read on its own (a part, a line the turn rewrote)."""
    kept = current_turn_reading()
    if kept is not None and kept.text == text:
        return kept.teaching
    return is_teaching_request(text)
