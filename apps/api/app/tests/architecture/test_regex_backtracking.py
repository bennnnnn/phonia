"""No module-level pattern backtracks exponentially on a short run of one character.

``(?:[\\s,:=.]+|of\\b)*`` can split a run of commas 2^n ways, and a failed ``fullmatch`` tries
every split: 22 commas in a physics question held the event loop for 0.3 s and each comma
doubled it, so one message could freeze an API machine for hours. ``search`` alone never sees
it (an empty match at position 0 succeeds at once), so each pattern is also anchored at both
ends. Each run grows two characters at a time and stops at the first slow call: a linear
pattern takes microseconds at the longest run, an exponential one crosses the budget long
before, so the test fails clearly instead of hanging.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import time

import app.modules as modules_package
import app.services as services_package

_BUDGET_SECONDS = 0.05
_RUNS = range(4, 27, 2)
# A character no pattern accepts, so the anchored match has to fail and backtrack.
_STOP = "\x00"
_SHAPES = (" ", ",", ", ", ".", ". ", ":", "=", "-", "(", "1", "1 ", "a", "a ", "of ", "x", "\n")
# A lead the pattern must get past before the run: a root sign before spaces, and a
# choice label before more of them ("A)!" then " a)!" again and again).
_LEADS = ("", "\u221a", "A)!")
_LED_SHAPES = {"": _SHAPES, "\u221a": (" ",), "A)!": (" a)!",)}


def _module_patterns() -> dict[str, re.Pattern[str]]:
    """Every compiled pattern a module under ``app.modules`` or ``app.services`` keeps at its top."""
    found: dict[tuple[str, int], tuple[str, re.Pattern[str]]] = {}
    for package in (modules_package, services_package):
        for info in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
            module = importlib.import_module(info.name)
            for name, value in vars(module).items():
                candidates = value if isinstance(value, tuple | list) else (value,)
                for index, candidate in enumerate(candidates):
                    if isinstance(candidate, re.Pattern) and isinstance(candidate.pattern, str):
                        label = f"{info.name}.{name}[{index}]"
                        found.setdefault((candidate.pattern, candidate.flags), (label, candidate))
    return dict(found.values())


def _timed(attempt: object, text: str) -> float:
    """Seconds one call takes; a slow one is timed again, so a pause on the runner is not a fail."""
    assert callable(attempt)
    best = float("inf")
    for _ in range(2):
        start = time.perf_counter()
        attempt(text)
        best = min(best, time.perf_counter() - start)
        if best <= _BUDGET_SECONDS:
            break
    return best


def test_no_pattern_backtracks_exponentially_on_a_short_run() -> None:
    patterns = _module_patterns()
    assert len(patterns) > 1_000, "the scan should see the subject readers' tables"
    slow = []
    for label, pattern in patterns.items():
        for lead in _LEADS:
            for shape in _LED_SHAPES[lead]:
                for attempt in (pattern.fullmatch, pattern.match, pattern.search):
                    for run in _RUNS:
                        elapsed = _timed(attempt, lead + shape * run + _STOP)
                        if elapsed > _BUDGET_SECONDS:
                            slow.append(
                                f"{label}.{attempt.__name__} on {lead!r} + {shape!r} x{run}: "
                                f"{elapsed:.2f}s"
                            )
                            break
    assert not slow, "patterns that backtrack exponentially:\n" + "\n".join(slow)
