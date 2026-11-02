"""Which SymPy solves ran out of time inside a block (``recording``).

A chat turn records its pre-solve so its tool loop does not run the same solve
again: one that ran out of time once does again, a whole tool round later.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_timed_out: ContextVar[list[str] | None] = ContextVar("math_solve_timeouts", default=None)


@contextmanager
def recording() -> Iterator[list[str]]:
    """Collect the kind of each solve that times out inside this block, in this
    task and the tasks it starts."""
    kinds: list[str] = []
    token = _timed_out.set(kinds)
    try:
        yield kinds
    finally:
        _timed_out.reset(token)


def note(kind: str) -> None:
    """A solve of this kind ran out of time (kept only while ``recording``)."""
    kinds = _timed_out.get()
    if kinds is not None:
        kinds.append(kind)
