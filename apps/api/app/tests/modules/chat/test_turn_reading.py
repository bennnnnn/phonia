"""A message is read off the event loop: a slow read never stalls the machine.

One maths question once held a machine's event loop for 56 s, and every WebSocket,
SSE stream and health check with it (code-health audit SCALE-01). These run on the
tests' thread executor, which schedules as the process pool does.
"""

from __future__ import annotations

import asyncio
import contextvars
import pickle
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from app.core.config import Settings
from app.core.readings import begin_turn, read_off_loop
from app.core.sympy_executor import set_sympy_executor
from app.modules.chat.related_questions import follow_up_topic
from app.modules.chat.turn_prep.followups import read_prompt_inputs
from app.modules.chat.turn_prep.intents import plan_turn
from app.modules.chat.turn_prep.reading import plan_of, read_turn, read_turn_message
from app.modules.math.tools.prompt import build_math_augmentation
from app.modules.physics.prompt import build_physics_augmentation
from app.modules.turn_reading.plan import TurnPlan, single_plan
from app.modules.turn_reading.turn import current_turn_reading
from app.services.subjects.dispatch import detect_subject, read_direct_reply
from app.tests.sympy_support import ThreadSympyExecutor


@pytest.fixture
def release() -> Iterator[threading.Event]:
    gate = threading.Event()
    yield gate
    gate.set()


async def _loop_ticks_while(work: asyncio.Future[object] | asyncio.Task[object]) -> int:
    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    ticker = asyncio.create_task(tick())
    try:
        await work
    finally:
        ticker.cancel()
    return ticks


async def test_a_slow_message_read_leaves_the_loop_free_and_reads_no_subject(
    monkeypatch: pytest.MonkeyPatch, release: threading.Event
) -> None:
    def slow_plan(text: str, *, chemistry_enabled: bool = True) -> TurnPlan:
        release.wait(5)
        return single_plan(text)

    monkeypatch.setattr("app.modules.chat.turn_prep.intents.plan_turn", slow_plan)
    begin_turn()
    read = asyncio.ensure_future(
        read_turn_message("solve 2x + 3 = 7", [], Settings(subject_read_timeout_seconds=0.3))
    )

    ticks = await _loop_ticks_while(read)

    assert ticks >= 10
    # The read gave up: nothing on the loop reads this message again this turn.
    assert detect_subject("solve 2x + 3 = 7") is None
    # The turn's reading says so, and plans the whole message as one request.
    reading = current_turn_reading()
    assert reading is not None and reading.plan_reason == "read_declined"
    assert reading.plan == single_plan("solve 2x + 3 = 7")


async def test_a_slow_maths_read_answers_with_the_unverified_note(
    monkeypatch: pytest.MonkeyPatch, release: threading.Event
) -> None:
    def slow_read(*_args: object, **_kwargs: object) -> None:
        release.wait(5)

    monkeypatch.setattr("app.modules.math.tools.prompt.read_math_request", slow_read)
    settings = Settings(math_tools_enabled=True, subject_read_timeout_seconds=0.3)
    begin_turn()
    work = asyncio.ensure_future(build_math_augmentation("graph y = 9^9^9 + x", settings))

    ticks = await _loop_ticks_while(work)

    note, verified = work.result()
    assert ticks >= 10
    assert verified is None
    assert note is not None and "Do NOT claim the answer was verified" in note


async def test_a_message_read_once_answers_the_sync_readers() -> None:
    begin_turn()
    await read_turn_message("A 2 kg ball falls 5 m. Find its speed.", [], Settings())

    assert detect_subject("A 2 kg ball falls 5 m. Find its speed.") == "physics"


class _PicklingExecutor(ThreadSympyExecutor):
    """The thread executor, with the process boundary's pickling on the way in and out."""

    async def run(self, fn: Any, *args: Any, timeout: float) -> Any:  # noqa: ASYNC109 - implements it
        # This process's own objects, round-tripped as the pool does (S301: no outside data).
        fn, args = pickle.loads(pickle.dumps((fn, args)))  # noqa: S301
        result = await super().run(fn, *args, timeout=timeout)
        return pickle.loads(pickle.dumps(result))  # noqa: S301


@pytest.fixture
def pickling_pool() -> Iterator[None]:
    set_sympy_executor(_PicklingExecutor(max_workers=1))
    yield
    set_sympy_executor(None)


async def test_every_read_crosses_the_process_boundary(pickling_pool: None) -> None:
    settings = Settings(math_tools_enabled=True)
    exchange = [
        {"role": "user", "content": "solve 2x + 3 = 7"},
        {"role": "assistant", "content": "x = 2"},
    ]
    begin_turn()
    car = "A car goes from 0 to 100 km/h in 8 s. Find its acceleration"
    await read_turn_message(car, exchange, settings)
    assert detect_subject(car) == "physics"

    note, verified = await build_math_augmentation("solve 2x + 3 = 7", settings)
    assert verified is not None and note is not None
    reply = await read_direct_reply(verified, "solve 2x + 3 = 7", settings)
    assert reply is not None and "x = 2" in reply

    _note, physics, failed = await build_physics_augmentation(
        "A 2 kg ball falls 5 m. Find its speed.", settings
    )
    assert physics is not None and not failed
    assert await read_off_loop(read_prompt_inputs, "how?", exchange, timeout=3) == "math"
    assert await read_off_loop(
        follow_up_topic, "solve 2x + 3 = 7", "x = 2", exchange, allow_general=True, timeout=3
    ) == ("subject", "solve 2x + 3 = 7")


async def test_a_turn_reads_its_plan_once_and_callers_read_it() -> None:
    settings = Settings()
    two = "switch to dark mode and tell me a joke"
    begin_turn()
    await read_turn_message(two, [], settings)

    reading = current_turn_reading()
    assert reading is not None and reading.plan.multi
    assert reading.plan_reason == "several_requests"
    # Asked again, the turn's reading answers: nothing is planned twice.
    assert read_turn(two, settings) is reading
    assert plan_of(two, settings) is reading.plan
    # Another text, or the same text read without chemistry, is not this reading.
    assert not reading.reads("tell me a joke", chemistry_enabled=True)
    assert not reading.reads(two, chemistry_enabled=False)


async def test_one_request_is_read_as_one() -> None:
    begin_turn()
    await read_turn_message("solve 2x + 3 = 7", [], Settings())

    reading = current_turn_reading()
    assert reading is not None and not reading.plan.multi
    assert reading.plan_reason == "one_request"


def test_outside_a_turn_a_plan_is_read_from_its_text() -> None:
    plan = contextvars.Context().run(plan_of, "tell me a joke", Settings())

    assert plan.texts() == ("tell me a joke",)


def _gives_up() -> bool:
    raise RuntimeError("the pool read gave up")


async def test_a_plan_read_before_a_read_gave_up_is_kept() -> None:
    two = "switch to dark mode and tell me a joke"
    begin_turn()
    await read_off_loop(plan_turn, two, chemistry_enabled=True, timeout=3)
    # A later pool read gives up: the turn's readings decline from here on.
    assert await read_off_loop(_gives_up, timeout=3) is None

    reading = read_turn(two, Settings())

    # The plan the pool already read stands, as plan_turn's own memo answers it.
    assert reading.plan.multi and reading.plan_reason == "several_requests"
    assert plan_of(two, Settings()).multi


async def test_a_regenerate_turn_reads_its_own_plan() -> None:
    settings = Settings()
    begin_turn()
    await read_turn_message("switch to dark mode and tell me a joke", [], settings)
    # The next turn regenerates another message: it reads that one, not the last turn's.
    begin_turn()
    await read_turn_message("solve 2x + 3 = 7", [], settings)

    reading = current_turn_reading()
    assert reading is not None and reading.text == "solve 2x + 3 = 7"
    assert not reading.plan.multi
    assert plan_of("solve 2x + 3 = 7", settings) is reading.plan


async def test_another_text_inside_a_turn_plans_itself() -> None:
    settings = Settings()
    two = "switch to dark mode and tell me a joke"
    begin_turn()
    await read_turn_message(two, [], settings)
    # Another line (an earlier one, a part) is read in the pool like any reading.
    await read_off_loop(plan_turn, "tell me a joke", chemistry_enabled=True, timeout=3)

    other = plan_of("tell me a joke", settings)

    reading = current_turn_reading()
    assert reading is not None and other is not reading.plan
    assert other.texts() == ("tell me a joke",)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("teach me how recursion works", "teach"),
        ("", "no_cue"),
        ("What is a python dictionary?", "no_cue"),
        ("teach me " + "very " * 100 + "much", "too_long"),
        ("Give me a 4-week roadmap to learn Python", "no_cue"),
        ("teach me python in 30 days", "learning_plan"),
        ("teach me by asking questions", "preference"),
        ("Teach me how to bake bread step by step", "procedure"),
    ],
)
def test_teaching_names_why(text: str, reason: str) -> None:
    from app.modules.turn_reading.teaching import is_teaching_request, teaching_reason

    assert teaching_reason(text) == reason
    assert is_teaching_request(text) is (reason == "teach")


async def test_teaching_is_the_turns_reading_for_its_message_and_read_for_any_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.turn_reading import turn
    from app.modules.turn_reading.teaching import is_teaching_request

    settings = Settings()
    begin_turn()
    await read_turn_message("teach me how recursion works", [], settings)
    read: list[str] = []

    def spy(text: str) -> bool:
        read.append(text)
        return is_teaching_request(text)

    monkeypatch.setattr(turn, "is_teaching_request", spy)

    reading = current_turn_reading()
    assert reading is not None and reading.teaching and reading.teaching_reason == "teach"
    # The turn's message answers from the reading: the reader is not run again.
    assert turn.teaching_of("teach me how recursion works") is True
    assert read == []
    # Another text is read on its own: a part, a rewritten line.
    assert turn.teaching_of("What is a python dictionary?") is False
    assert read == ["What is a python dictionary?"]
    # The next turn's reading is its own: the last turn's message is read again.
    begin_turn()
    await read_turn_message("What is a python dictionary?", [], settings)
    read.clear()
    assert turn.teaching_of("What is a python dictionary?") is False
    assert turn.teaching_of("teach me how recursion works") is True
    assert read == ["teach me how recursion works"]


@pytest.mark.parametrize(
    ("text", "chemistry", "subject", "reason"),
    [
        ("for (int i = 1; i <= 3; i++) { sum += i; }", True, None, "code"),
        (
            "A car accelerates from 0 to 20 m/s in 4 s. Find its acceleration.",
            True,
            "physics",
            "physics",
        ),
        ("Solve 2x + 3 = 7", True, "math", "math"),
        ("What is the pH of 0.01 M HCl?", True, "chemistry", "chemistry_closed"),
        ("What is the pH of 0.01 M HCl?", False, None, "chemistry_off"),
        ("What should I cook tonight?", True, None, "none"),
    ],
)
def test_the_subject_names_the_step_that_decided_it(
    text: str, chemistry: bool, subject: str | None, reason: str
) -> None:
    from app.services.subjects.dispatch import detect_subject, read_subject_reason

    found = read_subject_reason(text, False, chemistry)
    assert found is not None
    assert (found.subject, found.reason) == (subject, reason)
    assert detect_subject(text, chemistry_enabled=chemistry) == subject


async def test_the_subject_is_the_turns_reading_for_its_message_and_read_for_any_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.chat.turn_prep import reading as turn_reading_prep
    from app.services.subjects import dispatch

    settings = Settings()
    message = "A car accelerates from 0 to 20 m/s in 4 s. Find its acceleration."
    begin_turn()
    await read_turn_message(message, [], settings)
    asked: list[tuple[str, bool, bool]] = []
    detect = dispatch.detect_subject

    def spy(
        text: str, *, has_image_attachment: bool = False, chemistry_enabled: bool = True
    ) -> Any:
        asked.append((text, has_image_attachment, chemistry_enabled))
        return detect(
            text, has_image_attachment=has_image_attachment, chemistry_enabled=chemistry_enabled
        )

    monkeypatch.setattr(dispatch, "detect_subject", spy)

    reading = current_turn_reading()
    assert reading is not None
    assert (reading.subject, reading.subject_reason) == ("physics", "physics")
    # The turn's message with the turn's flags answers from the reading.
    assert turn_reading_prep.subject_of(message) == "physics"
    assert asked == []
    # Other flags, or another text, are read as before.
    assert turn_reading_prep.subject_of(message, has_image_attachment=True) == "physics"
    assert turn_reading_prep.subject_of("Solve 2x + 3 = 7") == "math"
    assert asked == [(message, True, True), ("Solve 2x + 3 = 7", False, True)]


async def test_the_turns_photo_reads_its_subject_again_after_turn_load() -> None:
    # Turn load reads the message before it knows the photo; the prompt reads it with it.
    settings = Settings()
    begin_turn()
    await read_turn_message("solve this", [], settings)
    before = current_turn_reading()
    assert before is not None
    assert (before.subject, before.subject_reason) == (None, "none")

    await read_turn_message("solve this", [], settings, has_image_attachment=True)
    reading = current_turn_reading()
    assert reading is not None
    assert (reading.subject, reading.subject_reason) == ("math", "math")
    assert reading.has_image_attachment and reading.plan == before.plan
    # A caller that names no flag (the trace) takes the turn's reading as it stands.
    assert read_turn("solve this", settings) is reading


async def test_a_subject_the_pool_did_not_read_stays_unknown_in_the_reading() -> None:
    begin_turn()
    reading = read_turn("Solve 2x + 3 = 7", Settings())

    assert reading.subject is None and reading.subject_reason == "not_read"
    assert not reading.knows_subject_of(
        "Solve 2x + 3 = 7", has_image_attachment=False, chemistry_enabled=True
    )
