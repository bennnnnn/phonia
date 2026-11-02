"""The physics corpus: no verified answer is wrong, and coverage only grows."""

from __future__ import annotations

import math

import pytest

from app.core.config import Settings
from app.modules.physics import build_verified_physics_block, extract_physics_intent, needs_physics
from app.modules.physics.block import _solve_requested_quantities
from app.modules.physics.solvers.si import to_si
from app.tests.modules.physics.corpus import (
    ANSWERABLE,
    COVERAGE_FLOOR,
    MUST_DECLINE,
    NOT_PHYSICS,
    Case,
)

_SETTINGS = Settings(math_tools_enabled=True)
# Result spellings Pint reads as something else: "D" is a debye.
_RESULT_UNITS = {"D": "1/m", "deg": "degree"}


def _si(value: float, unit: str) -> float:
    return to_si(value, _RESULT_UNITS.get(unit, unit))


def _verified_values(question: str) -> list[float] | None:
    """SI values of a verified answer, or None when the question declines."""
    intent = extract_physics_intent(question)
    if intent is None or build_verified_physics_block(intent, _SETTINGS) is None:
        return None
    result = _solve_requested_quantities(intent)
    return [_si(item.value, item.unit) for item in result.quantities]


def _matches(case: Case, values: list[float]) -> bool:
    assert case.expected is not None
    if len(values) < len(case.expected):
        return False
    return all(
        math.isclose(got, _si(want, unit), rel_tol=case.rel, abs_tol=1e-12)
        for got, (want, unit) in zip(values, case.expected, strict=False)
    )


@pytest.mark.parametrize("case", ANSWERABLE, ids=[case.question[:60] for case in ANSWERABLE])
def test_a_verified_answer_is_never_wrong(case: Case) -> None:
    values = _verified_values(case.question)
    if values is not None:
        assert _matches(case, values), f"verified {values}, expected {case.expected}"


@pytest.mark.parametrize("case", MUST_DECLINE, ids=[case.question[:60] for case in MUST_DECLINE])
def test_an_ambiguous_question_declines(case: Case) -> None:
    assert _verified_values(case.question) is None


@pytest.mark.parametrize("text", NOT_PHYSICS)
def test_ordinary_text_is_not_physics(text: str) -> None:
    assert needs_physics(text) is False


def test_coverage_never_drops() -> None:
    answered = [case for case in ANSWERABLE if _verified_values(case.question) is not None]
    print(f"physics corpus coverage: {len(answered)}/{len(ANSWERABLE)}")
    missing = [case.question for case in ANSWERABLE if case not in answered]
    assert len(answered) >= COVERAGE_FLOOR, f"Unanswered corpus questions: {missing}"
