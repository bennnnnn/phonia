"""The math gate and extraction read a line once between them (ES-15).

The gate asks its lexical signals first and a chosen few extractors last; the
extraction step that follows a yes reuses those reads instead of running the
extractors again.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from types import FrameType

import pytest

from app.modules.math.match import needs_symbolic
from app.modules.math.schemas import MathIntent
from app.modules.math.tools import extract_math_intent, needs_symbolic_math
from app.modules.math.tools.extractors import readings
from app.modules.math.tools.school.function_value import extract_function_value_intent
from app.modules.math.tools.school.probability import extract_at_least_one_intent
from app.modules.math.tools.school.units import extract_how_many_in_intent


@pytest.fixture(autouse=True)
def _fresh_reads() -> Iterator[None]:
    readings._read.cache_clear()
    yield
    readings._read.cache_clear()


def _runs(reader: Callable[..., object], action: Callable[[], object]) -> int:
    """How many times ``reader`` really ran (a cache hit never enters it)."""
    code = reader.__code__
    calls = 0

    def profile(frame: FrameType, event: str, _arg: object) -> None:
        nonlocal calls
        if event == "call" and frame.f_code is code:
            calls += 1

    previous = sys.getprofile()
    sys.setprofile(profile)
    try:
        action()
    finally:
        sys.setprofile(previous)
    return calls


@pytest.mark.parametrize(
    ("text", "reader", "kind"),
    [
        # A reader the registry runs inside the unit extractor.
        ("how many seconds in a day", extract_how_many_in_intent, "unit"),
        # One the registry runs inside the probability extractor.
        (
            "the probability of getting at least one head in 3 coin flips",
            extract_at_least_one_intent,
            "probability",
        ),
        # One the registry runs itself.
        ("if f(x) = 3x + 1, what is f(2)", extract_function_value_intent, "arithmetic"),
    ],
)
def test_the_gate_and_extraction_read_a_line_once(
    text: str, reader: Callable[[str], MathIntent | None], kind: str
) -> None:
    found: list[MathIntent | None] = []

    def turn() -> None:
        assert needs_symbolic_math(text)
        found.append(extract_math_intent(text))

    assert _runs(reader, turn) == 1
    assert found[0] is not None and found[0].kind == kind


def test_a_lexical_signal_answers_before_any_extractor_runs() -> None:
    assert needs_symbolic("solve 2x+3=7")
    assert readings._read.cache_info().currsize == 0


def test_the_whole_registry_is_not_a_gate() -> None:
    """Some registry extractors read prose; the gate keeps it away from them."""
    assert extract_math_intent("compare React and Vue") is not None
    assert not needs_symbolic_math("compare React and Vue")


def test_each_reader_runs_once_per_line_and_each_caller_gets_its_own_copy() -> None:
    calls: list[str] = []

    def counting(text: str) -> MathIntent:
        calls.append(text)
        return MathIntent(kind="arithmetic", expr="2+2", operation="solve")

    first = readings.read(counting, "what is 2+2")
    second = readings.read(counting, "what is 2+2")
    assert calls == ["what is 2+2"]
    assert first is not None and second is not None and first is not second
    first.expr = "3+3"
    assert second.expr == "2+2"
    readings.read(counting, "what is 3+3")
    assert calls == ["what is 2+2", "what is 3+3"]
