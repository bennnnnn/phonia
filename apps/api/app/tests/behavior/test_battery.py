"""Every battery prompt is routed the way its case expects.

A case with a ``gap`` is a known miss: it is an expected failure until the gap is
fixed, and strict, so the fix has to delete the ``gap`` line in the same change.
Run ``./scripts/dev.sh battery`` to see the replies a real model writes.
"""

from __future__ import annotations

import pytest

from app.tests.behavior.cases import CASES, CATEGORIES, Case
from app.tests.behavior.harness import HINTS, mismatches, route_case


def _param(case: Case) -> object:
    marks = [pytest.mark.xfail(reason=case.gap, strict=True)] if case.gap else []
    return pytest.param(case, id=case.id, marks=marks)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [_param(case) for case in CASES])
async def test_battery_routes_each_prompt(case: Case, thread_sympy_executor: None) -> None:
    route = await route_case(case)
    problems = mismatches(case.expect, route)
    assert not problems, f"{case.prompt!r} → {route.summary()}: " + "; ".join(problems)


def test_battery_cases_are_well_formed() -> None:
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids)), "case ids repeat"
    for case in CASES:
        assert case.category in CATEGORIES, case.id
        assert case.prompt.strip() and case.good.strip(), case.id
        unknown = {*case.expect.hints, *case.expect.no_hints} - {*HINTS, "programming_lesson"}
        assert not unknown, f"{case.id}: unknown hints {unknown}"
    assert {case.category for case in CASES} == set(CATEGORIES)
