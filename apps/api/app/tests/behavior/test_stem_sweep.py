"""Every STEM sweep question is answered right or left to the model, never wrong.

The STEM sweep (``stem_sweep.py``) runs homework questions through the real
chat path and reads the verified answer card. A wrong number, a misread turn, a
reply out of shape or a broken picture fails its own test. Questions the solver
declines, and pictures it does not draw, are coverage: ``stem_snapshot.json``
names every question each subject answers and draws, so a change that answers
one question fewer fails even when it answers another more (a count would stay
level). A change that answers more records it: ``UPDATE_STEM_SNAPSHOT=1``. A
``gap`` entry is a known miss: a strict expected failure, so the fix deletes its
``gap`` line.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.modules.physics.solvers.motion_scenes import vertical_scene
from app.tests.behavior.stem_sweep import (
    SUBJECT_NAMES,
    Entry,
    Outcome,
    answered,
    check_visuals,
    drawn,
    load,
    run,
    run_entry,
)

SUBJECTS = ("chemistry", "math", "physics")
SNAPSHOT = Path(__file__).with_name("stem_snapshot.json")
EXPECTS = {"answer", "explain", "decline", "not_subject"}

ENTRIES = [(subject, entry) for subject in SUBJECTS for entry in load(subject)]


def _param(subject: str, entry: Entry) -> object:
    marks = [pytest.mark.xfail(reason=entry.gap, strict=True)] if entry.gap else []
    return pytest.param(subject, entry, id=f"{subject}:{entry.id}", marks=marks)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("subject", "entry"), [_param(subject, entry) for subject, entry in ENTRIES]
)
async def test_stem_turn_is_never_wrong(
    subject: str, entry: Entry, thread_sympy_executor: None
) -> None:
    outcome = await run_entry(entry, SUBJECT_NAMES[subject])
    assert not outcome.critical, f"{entry.prompt!r}: " + "; ".join(
        f"{problem.kind}: {problem.text}" for problem in outcome.critical
    )


def _covered(outcomes: list[Outcome]) -> dict[str, list[str]]:
    return {
        "answered": sorted(outcome.entry.id for outcome in answered(outcomes)),
        "drawn": sorted(outcome.entry.id for outcome in drawn(outcomes)),
    }


@pytest.mark.asyncio
# One test reads a whole subject's corpus (physics: 833 turns, ~15 s locally): the suite's
# 60 s hang limit is for one turn, and a loaded CI runner under coverage passed it (2026-10-31).
@pytest.mark.timeout(600)
@pytest.mark.parametrize("subject", SUBJECTS)
async def test_stem_coverage_matches_its_snapshot(
    subject: str, thread_sympy_executor: None
) -> None:
    covered = _covered(await run(load(subject), SUBJECT_NAMES[subject]))
    recorded = json.loads(SNAPSHOT.read_text())
    if os.environ.get("UPDATE_STEM_SNAPSHOT") == "1":
        recorded[subject] = covered
        SNAPSHOT.write_text(json.dumps(recorded, indent=1, sort_keys=True) + "\n")
        return
    held = recorded.get(subject, {})
    flips = [
        line
        for kind, ids in covered.items()
        for line in _flips(subject, kind, set(held.get(kind, [])), set(ids))
    ]
    assert not flips, "\n".join(
        [
            *flips,
            f"See one: uv run python -m app.tests.behavior.stem_sweep {subject} --show --only <id>",
            "A change meant to answer more: UPDATE_STEM_SNAPSHOT=1, then commit stem_snapshot.json",
        ]
    )


def _flips(subject: str, kind: str, was: set[str], now: set[str]) -> list[str]:
    def named(ids: set[str]) -> str:
        shown = sorted(ids)
        return ", ".join(shown[:20]) + (f" and {len(shown) - 20} more" if len(shown) > 20 else "")

    lines = []
    if was - now:
        lines.append(f"{subject}: {len(was - now)} no longer {kind}: {named(was - now)}")
    if now - was:
        lines.append(f"{subject}: {len(now - was)} newly {kind}: {named(now - was)}")
    return lines


@pytest.mark.parametrize("subject", SUBJECTS)
def test_stem_corpus_is_well_formed(subject: str) -> None:
    entries = load(subject)
    ids = [entry.id for entry in entries]
    assert len(ids) == len(set(ids)), "entry ids repeat"
    for entry in entries:
        assert entry.expect in EXPECTS, entry.id
        assert entry.prompt.strip(), entry.id
        assert entry.checked == (entry.expect == "answer"), entry.id
        assert entry.shared in {None, *SUBJECT_NAMES} - {subject}, entry.id


@pytest.mark.parametrize(
    ("trajectory_type", "duplicate"),
    [("velocity_vs_time", False), ("position_vs_time", True), ("parametric", True)],
)
def test_only_a_path_graph_beside_a_fall_is_the_same_picture_twice(
    trajectory_type: str, duplicate: bool
) -> None:
    """A v-t line says something the fall does not (its slope is g); a path curve does not."""
    scene = vertical_scene(10.0, 0.0, 9.81, 1.43, ground=True)
    assert scene is not None
    graph = {"type": "trajectory", "trajectory_type": trajectory_type, "points": [[0, 0], [1, 1]]}
    reply = f"```simulation\n{scene.model_dump_json()}\n```\n\n```graph\n{json.dumps(graph)}\n```"
    _kinds, problems = check_visuals(reply)
    assert any(problem.kind == "duplicate_visual" for problem in problems) is duplicate
