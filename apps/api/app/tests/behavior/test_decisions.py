"""The decision diff holds still on one commit, and names what changed between two."""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.chat.turn_trace import plain_record
from app.tests.behavior import decisions, stem_sweep, sweep
from app.tests.behavior.cases import CASES

# A few turns of every corpus. cc-001 and cc-002 are sweep replies the finalize step rewrites:
# the trace begun when the turn is read also holds what its passes changed.
_REWRITTEN = ("cc-001", "cc-002")
_SAMPLE = {
    *(case.id for case in CASES[:6]),
    *(entry.id for entry in sweep.load()[:12]),
    *_REWRITTEN,
    *(entry.id for subject in stem_sweep.SUBJECT_NAMES for entry in stem_sweep.load(subject)[:4]),
}


@pytest.mark.asyncio
async def test_two_dumps_of_the_same_turns_are_identical(thread_sympy_executor: None) -> None:
    first = await decisions.collect(only=_SAMPLE)
    second = await decisions.collect(only=_SAMPLE)

    assert first == second
    assert decisions.diff(first, second) == {}
    assert set(first) == set(decisions.CORPORA)
    records = [record for turns in first.values() for record in turns.values()]
    assert records and all(plain_record(record) for record in records)
    # Decisions, not timings: two runs differ in how long they took, never in these.
    assert not any(key.endswith("_ms") for record in records for key in record)
    assert all(first["sweep"][turn]["passes_changed"] for turn in _REWRITTEN)
    assert all(record.get("prompt_rules") for record in records)


def test_a_turn_with_no_trace_is_recorded_as_crashed() -> None:
    assert decisions.decision_record(None) == {"crashed": True}


def test_the_diff_groups_changed_turns_by_field() -> None:
    before: dict[str, dict[str, dict[str, Any]]] = {
        "math": {
            "a1": {"route": "auto.math", "solver": {"op": "solve"}},
            "a2": {"route": "auto.math", "plan": ["ask"]},
        },
        "sweep": {"s1": {"route": "auto.everyday"}},
    }
    after: dict[str, dict[str, dict[str, Any]]] = {
        "math": {
            "a1": {"route": "auto.math", "solver": {"op": "simplify"}},
            "a2": {"route": "auto.everyday", "plan": ["ask"]},
        },
        "sweep": {"s2": {"route": "auto.everyday"}},
    }

    changed = decisions.diff(before, after)

    assert changed == {
        "solver": ['math:a1: {"op":"solve"} -> {"op":"simplify"}'],
        "route": ['math:a2: "auto.math" -> "auto.everyday"'],
        "(turn)": ["sweep:s1: only before", "sweep:s2: only after"],
    }
    shown = decisions.report(changed, limit=1)
    assert shown.startswith("4 turns changed, in 3 fields")
    assert decisions.report({}, limit=1) == "no decision changed"


def test_a_field_a_change_adds_is_listed_not_counted_as_changed() -> None:
    before: dict[str, dict[str, dict[str, Any]]] = {"sweep": {"s1": {"route": "auto.everyday"}}}
    after: dict[str, dict[str, dict[str, Any]]] = {
        "sweep": {"s1": {"route": "auto.everyday", "plan_reason": "one_request"}}
    }

    assert decisions.diff(before, decisions._without(after, ["plan_reason"])) == {}
    assert decisions.report_added(before, after, ["plan_reason"]) == (
        'added plan_reason: "one_request" ×1'
    )
    # A field one turn already had is no addition.
    assert "ERROR: 1 turns had it before" in decisions.report_added(after, after, ["plan_reason"])
