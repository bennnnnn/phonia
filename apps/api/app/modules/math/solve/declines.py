"""Maths declines: a failed SymPy step drops its trace and says why; a bug still raises in tests.

A decline is designed behaviour. When SymPy cannot do a step here (no polynomial form, an
unsolvable equation, a sign it cannot decide), the check or trace that needed it is dropped and
the turn keeps its model path. The same ``except Exception`` would also swallow an
``AttributeError`` or ``NameError`` from a refactor, so this module is the one place that tells
the two apart:

- ``@declines(default)`` wraps a function whose whole body is the attempt;
- ``with sympy_decline() as declined:`` wraps part of one; ``declined`` is true afterwards when
  the block failed, so the caller returns its own default (a fresh ``[]`` each time).

Each decline is logged at DEBUG (where, the exception type, a short message).

Outside strict mode every ``Exception`` declines except ``TimeoutError`` (the SymPy pool's
timeout), as the plain ``except Exception`` it replaces did. A ``BaseException`` (cancellation,
``KeyboardInterrupt``) always passes through.

With ``RECALL_STRICT_DECLINES=1`` (the test run sets it in ``app/tests/conftest.py``) a
programming error raises instead: an ``AttributeError``, ``NameError`` (``UnboundLocalError``),
``KeyError``, ``ImportError``, ``AssertionError`` or ``TypeError`` raised in our own code. The
same types raised inside SymPy or mpmath are SymPy failing on the input, so they still decline:
an exception class SymPy or mpmath defines, or one whose nearest frame outside the standard
library is SymPy's, mpmath's or code ``lambdify`` generated (``bool(x < 0)`` on a symbolic
``x`` raises its ``TypeError`` in SymPy). The nearest ``app`` frame makes it ours. Everything
else (``ValueError``, ``ArithmeticError``, ``RecursionError``, ``NotImplementedError``,
``IndexError``, SymPy's own errors) declines in both modes.
"""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Callable
from types import TracebackType

logger = logging.getLogger(__name__)

STRICT_ENV = "RECALL_STRICT_DECLINES"

# Raised in our own code these are bugs, not maths a SymPy step could not do.
_PROGRAMMING_ERRORS: tuple[type[Exception], ...] = (
    AttributeError,
    NameError,
    KeyError,
    ImportError,
    AssertionError,
    TypeError,
)
_MATHS_LIBRARIES = frozenset({"sympy", "mpmath"})
_LAMBDIFY_FILE = "<lambdifygenerated"
_MESSAGE_CHARS = 120


def strict_declines() -> bool:
    """True when a programming error must raise instead of declining (the test run)."""
    return os.environ.get(STRICT_ENV) == "1"


def _top_package(module: object) -> str:
    return module.split(".", 1)[0] if isinstance(module, str) else ""


def _raised_in_maths_library(tb: TracebackType | None) -> bool:
    """Whether, from the raise outward, a SymPy or mpmath frame comes before one of ours.

    Standard-library and other packages' frames are passed over, so SymPy calling the standard
    library still counts as SymPy, and our code calling it still counts as ours.
    """
    frames = []
    while tb is not None:
        frames.append(tb.tb_frame)
        tb = tb.tb_next
    for frame in reversed(frames):
        if frame.f_code.co_filename.startswith(_LAMBDIFY_FILE):
            return True
        package = _top_package(frame.f_globals.get("__name__"))
        if package in _MATHS_LIBRARIES:
            return True
        if package == "app":
            return False
    return False


def is_programming_error(exc: BaseException) -> bool:
    """An error our own code raised (a bug), not SymPy or mpmath failing on the input."""
    if not isinstance(exc, _PROGRAMMING_ERRORS):
        return False
    if _top_package(type(exc).__module__) in _MATHS_LIBRARIES:
        return False
    return not _raised_in_maths_library(exc.__traceback__)


def _declined(where: str, exc: BaseException) -> bool:
    """Record ``exc`` as a decline at ``where``; False when it must propagate instead."""
    if not isinstance(exc, Exception) or isinstance(exc, TimeoutError):
        return False
    if strict_declines() and is_programming_error(exc):
        return False
    name = type(exc).__name__
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("maths decline in %s: %s: %s", where, name, str(exc)[:_MESSAGE_CHARS])
    return True


def _qualified(module: object, qualname: str) -> str:
    return f"{module}.{qualname}" if isinstance(module, str) else qualname


def _block_where(tb: TracebackType | None) -> str:
    """The function running a ``with`` block: its traceback starts at that frame."""
    if tb is None:
        return "<unknown>"
    frame = tb.tb_frame
    return _qualified(frame.f_globals.get("__name__"), frame.f_code.co_qualname)


class Decline:
    """``with sympy_decline() as declined:``; ``declined`` is true once the block declined."""

    __slots__ = ("_where", "declined")

    def __init__(self, where: str | None) -> None:
        self._where = where
        self.declined = False

    def __enter__(self) -> Decline:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc is None:
            return False
        if not _declined(self._where or _block_where(tb), exc):
            return False
        self.declined = True
        return True

    def __bool__(self) -> bool:
        return self.declined


def sympy_decline(where: str | None = None) -> Decline:
    """Decline (log, count, swallow) a maths failure inside the ``with`` block.

    ``where`` names the attempt in the log and the counter; it defaults to the enclosing
    function's qualified name.
    """
    return Decline(where)


def declines[D, **P, R](default: D) -> Callable[[Callable[P, R]], Callable[P, R | D]]:
    """Return ``default`` when the wrapped function's maths fails (see the module docstring).

    ``default`` is returned as is, so it must be immutable (``None``, ``False``, a tuple); a
    list would be shared between calls. Use ``sympy_decline`` and return a fresh one instead.
    """
    if isinstance(default, list | dict | set):
        raise TypeError("declines() needs an immutable default; use sympy_decline() for a list")

    def decorate(fn: Callable[P, R]) -> Callable[P, R | D]:
        where = _qualified(fn.__module__, fn.__qualname__)

        @functools.wraps(fn)
        def attempt(*args: P.args, **kwargs: P.kwargs) -> R | D:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if not _declined(where, exc):
                    raise
                return default

        return attempt

    return decorate
