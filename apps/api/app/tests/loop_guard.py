"""Fail a test when production code reads a message, or runs SymPy, on the event loop.

One maths question once held a machine's event loop for 56 s, and every socket and
request on it with it (code-health audit SCALE-01). Readers run in the SymPy pool
(``app/core/readings.py``); this records the two ways back onto the loop:

- a ``@reading`` computed on the loop for production async code inside a turn whose
  message was read (it asked another text or argument than the read covered), reported by
  ``readings.on_loop_hooks``;
- a SymPy entry point (parse, sympify, solve, simplify, …) called there.

"Production async code" is the innermost ``async def`` on the stack: a test that calls a
reader from its own async body is not a finding. ``RECALL_STRICT_LOOP=0`` turns it off.
Installed when conftest imports this module, before the app imports SymPy's names.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import sys
from collections.abc import Callable
from types import FrameType
from typing import Any

from app.core import readings

STRICT = os.environ.get("RECALL_STRICT_LOOP", "1") != "0"
_COROUTINE_FLAGS = inspect.CO_COROUTINE | inspect.CO_ASYNC_GENERATOR
# What this test ran on the loop: "<what> from <async function>".
found: list[str] = []

_SYMPY_ENTRY_POINTS = (
    ("sympy.parsing.sympy_parser", "parse_expr"),
    ("sympy.core.sympify", "sympify"),
    ("sympy.solvers.solvers", "solve"),
    ("sympy.solvers.solveset", "solveset"),
    ("sympy.simplify.simplify", "simplify"),
    ("sympy.integrals.integrals", "integrate"),
    ("sympy.series.limits", "limit"),
    ("sympy.polys.polytools", "factor"),
)


def _production_caller() -> str | None:
    """``module.function`` of the innermost async def, when it is production code."""
    frame: FrameType | None = sys._getframe(2)
    while frame is not None:
        if frame.f_code.co_flags & _COROUTINE_FLAGS:
            module = frame.f_globals.get("__name__", "")
            if module.startswith("app.") and not module.startswith("app.tests"):
                return f"{module}.{frame.f_code.co_name}"
            return None
        frame = frame.f_back
    return None


def _on_loop(what: str) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    caller = _production_caller()
    if caller is not None:
        found.append(f"{what} from {caller}")


def _guarded(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    def guarded(*args: Any, **kwargs: Any) -> Any:
        _on_loop(name)
        return original(*args, **kwargs)

    guarded.__wrapped__ = original  # type: ignore[attr-defined]
    guarded.__name__ = getattr(original, "__name__", name)
    return guarded


def install() -> None:
    if not STRICT:
        return
    import sympy

    for module_name, attr in _SYMPY_ENTRY_POINTS:
        module = importlib.import_module(module_name)
        original = getattr(module, attr)
        if hasattr(original, "__wrapped__"):
            continue
        guarded = _guarded(f"sympy.{attr}", original)
        setattr(module, attr, guarded)
        # ``from sympy import solve`` binds the package's name.
        if getattr(sympy, attr, None) is original:
            setattr(sympy, attr, guarded)
    readings.on_loop_hooks.append(_on_loop_reading)


def _on_loop_reading(name: str, caller: str) -> None:
    # The reading already established that a production coroutine runs it on the loop.
    found.append(f"reading {name} from {caller}")
