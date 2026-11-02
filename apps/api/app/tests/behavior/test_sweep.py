"""Every sweep turn reaches the user the way its corpus entry expects.

The sweep (``sweep.py``) runs hundreds of real-sounding turns, each with a reply
a model might write, through routing and the finalize step. A rule that reads
the user's words wrongly shows up here: "Can you add 3 + 4 using the same
method?" answered "When should I remind you?". An entry with a ``gap`` is a
known miss and a strict expected failure until it is fixed.
"""

from __future__ import annotations

import pytest

from app.tests.behavior.sweep import EXPECTS, Entry, load, run_entry

ENTRIES = load()


def _param(entry: Entry) -> object:
    marks = [pytest.mark.xfail(reason=entry.gap, strict=True)] if entry.gap else []
    return pytest.param(entry, id=entry.id, marks=marks)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", [_param(entry) for entry in ENTRIES])
async def test_sweep_turn(entry: Entry, thread_sympy_executor: None) -> None:
    outcome = await run_entry(entry)
    assert not outcome.problems, (
        f"{entry.prompt!r}: " + "; ".join(outcome.problems) + f"\nfinal: {outcome.final[:300]!r}"
    )


def test_sweep_corpus_is_well_formed() -> None:
    ids = [entry.id for entry in ENTRIES]
    assert len(ids) == len(set(ids)), "entry ids repeat"
    assert len(ENTRIES) >= 500
    for entry in ENTRIES:
        assert set(entry.expects) <= EXPECTS, entry.id
        assert entry.prompt.strip(), entry.id
        assert entry.reply.strip() or entry.expect == "instant", entry.id
