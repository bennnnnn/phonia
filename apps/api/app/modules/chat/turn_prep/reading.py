"""Read the turn's message once, in the SymPy pool, before code on the event loop asks.

Routing, the prompt builder, the subject fetch, the tool loop and the finalize passes
all ask the same readings of the message: its plan, its subject, whether physics or
maths claims it, its maths and physics intents. ``ask_turn_readings`` asks each of them
in a pool worker, where a hostile message stops at the timeout, and the turn keeps the
answers (``app/core/readings.py``). Workers import this module, so it stays light:
nothing here may import the prompt, attachment or database stack.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from app.core.config import Settings
from app.core.readings import first_read, kept_reading, read_off_loop, readings_declined
from app.modules.turn_reading.plan import TurnPlan, single_plan
from app.modules.turn_reading.teaching import teaching_reason
from app.modules.turn_reading.turn import (
    PlanReason,
    TurnReading,
    current_turn_reading,
    keep_turn_reading,
    request_units,
)

if TYPE_CHECKING:
    from app.services.subjects.dispatch import SubjectName

# Exchanges a terse follow-up reaches back over (``math.followup``).
_FOLLOWUP_EXCHANGES = 4


def read_turn(
    content: str, settings: Settings, *, has_image_attachment: bool | None = None
) -> TurnReading:
    """The turn's reading of its message, built once from the pooled readings and kept.

    Its fields come from the readings ``ask_turn_readings`` made in the pool, so building
    it reads nothing on the loop: a subject the pool did not read stays unknown here.
    ``has_image_attachment`` None takes the kept reading whatever its flag; a flag the
    kept reading was not made with (turn load reads before it knows the turn's photo)
    builds it again, with the subject the pool read under that flag.
    """
    from app.modules.chat.turn_prep.intents import plan_turn
    from app.services.subjects.order import read_subject_reason

    chemistry = settings.chemistry_enabled
    kept = current_turn_reading()
    if (
        kept is not None
        and kept.reads(content, chemistry_enabled=chemistry)
        and has_image_attachment in (None, kept.has_image_attachment)
    ):
        return kept
    image = bool(has_image_attachment)
    # The pool's plan of the message first, as ``@reading`` answers: a later read that gave
    # up does not undo a plan already read.
    kept_plan = kept_reading(plan_turn, content, chemistry_enabled=chemistry)
    reason: PlanReason
    if kept_plan is None and readings_declined():
        # The pool gave up before planning it: the whole message is one request, as
        # ``plan_turn`` declines, and nothing plans it on the loop.
        plan, reason = single_plan(content), "read_declined"
    else:
        plan = kept_plan or plan_turn(content, chemistry_enabled=chemistry)
        reason = "several_requests" if plan.multi else "one_request"
    subject = kept_reading(read_subject_reason, content, image, chemistry)
    reading = TurnReading(
        content,
        chemistry,
        plan,
        reason,
        teaching_reason(content),
        has_image_attachment=image,
        subject=None if subject is None else subject.subject,
        subject_reason=_subject_reason(subject),
        place_requests=_place_requests(content, plan, image, chemistry),
    )
    keep_turn_reading(reading)
    return reading


def _place_requests(
    content: str, plan: TurnPlan, image: bool, chemistry: bool
) -> tuple[tuple[str, str | None], ...]:
    """The message's requests that ask about a place or the weather on their own words, each
    with the subject the pool read in it (``_read_place_requests``; None when the read gave
    up). A message of one request has none: it is the subject's, or no homework."""
    from app.modules.web_search import asks_about_a_place
    from app.services.subjects.order import read_subject_reason

    units = request_units(content, plan)
    if len(units) < 2:
        return ()
    found = []
    for unit in units:
        if asks_about_a_place(unit):
            read = kept_reading(read_subject_reason, unit, image, chemistry)
            found.append((unit, None if read is None else read.subject))
    return tuple(found)


def _subject_reason(subject: Any) -> str:
    if subject is not None:
        return str(subject.reason)
    return "read_declined" if readings_declined() else "not_read"


def subject_of(
    text: str, *, has_image_attachment: bool = False, chemistry_enabled: bool = True
) -> SubjectName | None:
    """The subject of ``text`` (``detect_subject``): the turn's own reading when it read
    ``text`` with these flags, else ``text`` read as before (a part, another line, other
    flags)."""
    from app.services.subjects.dispatch import detect_subject

    kept = current_turn_reading()
    if kept is not None and kept.knows_subject_of(
        text, has_image_attachment=has_image_attachment, chemistry_enabled=chemistry_enabled
    ):
        return cast("SubjectName | None", kept.subject)
    return detect_subject(
        text, has_image_attachment=has_image_attachment, chemistry_enabled=chemistry_enabled
    )


def plan_of(text: str, settings: Settings | None = None) -> TurnPlan:
    """The plan of ``text``: the turn's own plan when ``text`` is the turn's message.

    A caller holding another text (a line from the prompt the turn rewrote, an earlier
    line) reads that text's plan as before.
    """
    from app.modules.chat.turn_prep.intents import plan_turn

    chemistry = settings is None or settings.chemistry_enabled
    kept = current_turn_reading()
    if kept is not None and kept.reads(text, chemistry_enabled=chemistry):
        return kept.plan
    return plan_turn(text, chemistry_enabled=chemistry)


def ask_turn_readings(
    content: str,
    *,
    prior_user: str | None,
    prior_model: str | None,
    lesson_active: bool,
    has_image_attachment: bool,
    settings: Settings,
    earlier_lines: tuple[str, ...] = (),
) -> None:
    """Every reading the turn's sync code asks of its message. Runs in a pool worker."""
    from app.modules.chat.model_routing.route import route_chat_model
    from app.modules.chat.turn_prep.intents import plan_turn
    from app.services.subjects.dispatch import detect_subject
    from app.services.subjects.registry import subject_adapter

    chemistry = settings.chemistry_enabled
    maths = subject_adapter("math")
    plan = plan_turn(content, chemistry_enabled=chemistry)
    # The plan's parts too: the tool loop asks each whether it is maths.
    for text in dict.fromkeys((content, *plan.texts())):
        detect_subject(text)
        detect_subject(text, has_image_attachment=has_image_attachment, chemistry_enabled=chemistry)
        if maths.asks(text):
            maths.reads(text)
    maths.reads(content)
    subject_adapter("physics").reads(content)
    _read_place_requests(content, plan, has_image_attachment, chemistry)
    # The follow-up readers ask the subject of the user's earlier lines: a physics or
    # chemistry problem is not replayed through maths. Routing asks the line before this
    # one whenever the turn may inherit its lane. A money follow-up asks each line's plan,
    # to read it in the parts its own turn did.
    for text in earlier_lines:
        detect_subject(text)
        plan_turn(text, chemistry_enabled=chemistry)
    if prior_user:
        detect_subject(prior_user, chemistry_enabled=chemistry)
    route_chat_model(
        content,
        prior_user=prior_user,
        prior_model=prior_model,
        lesson_active=lesson_active,
        settings=settings,
    )


def _read_place_requests(
    content: str, plan: TurnPlan, has_image_attachment: bool, chemistry: bool
) -> None:
    """The subject of each request that asks about a place on its own words, so the turn
    knows whether it is part of the homework beside it (``web_search.homework``)."""
    from app.modules.web_search import asks_about_a_place
    from app.services.subjects.order import read_subject_reason

    units = request_units(content, plan)
    if len(units) < 2:
        return
    for unit in units:
        if asks_about_a_place(unit):
            read_subject_reason(unit, has_image_attachment, chemistry)


async def read_turn_message(
    content: str,
    recent: Sequence[Any],
    settings: Settings,
    *,
    has_image_attachment: bool = False,
) -> None:
    """Read the message (and the line before it, for routing) off the loop, for this turn,
    and keep the turn's reading of it (``read_turn``).

    Turn load reads it; turn prep asks again (a regenerate, the behavior harness) and
    pays only for what changed.
    """
    from app.modules.chat.model_routing.route import last_user_turn
    from app.modules.turn_reading.lesson_flow import active_lesson_step
    from app.services.problem_followup import message_role_content

    earlier = list(recent)
    # The message's own row may already be in the window: it is not the line before it.
    if earlier and message_role_content(earlier[-1]) == ("user", content):
        earlier.pop()
    prior_user, prior_model = last_user_turn(earlier)
    if first_read(("turn_message", content, prior_user, has_image_attachment)):
        await read_off_loop(
            ask_turn_readings,
            content,
            prior_user=prior_user,
            prior_model=prior_model,
            lesson_active=active_lesson_step(list(recent)) is not None,
            has_image_attachment=has_image_attachment,
            settings=settings,
            earlier_lines=_earlier_user_lines(earlier),
            timeout=settings.subject_read_timeout_seconds,
        )
    read_turn(content, settings, has_image_attachment=has_image_attachment)


def _earlier_user_lines(earlier: Sequence[Any]) -> tuple[str, ...]:
    """The user's lines in the last four exchanges, as far back as a follow-up looks."""
    from app.services.problem_followup import message_role_content

    lines: list[str] = []
    for message in reversed(earlier):
        role, text = message_role_content(message)
        if role == "user" and text and text.strip():
            lines.append(text)
            if len(lines) == _FOLLOWUP_EXCHANGES:
                break
    return tuple(lines)


def warm_pool_worker() -> None:
    """The pool warm-up: each subject's (maths' solve) and a message read, so a turn pays
    neither's imports.

    A worker starts cold at boot and again after a timeout kills it; the executor runs
    this first, outside any timeout.
    """
    from app.services.subjects.registry import SUBJECTS

    for subject in SUBJECTS:
        subject.warm()
    ask_turn_readings(
        "A car goes from 0 to 100 km/h in 8 s. Find a, and also solve 2x + 3 = 7",
        prior_user=None,
        prior_model=None,
        lesson_active=False,
        has_image_attachment=False,
        settings=Settings.model_validate({}),
    )
