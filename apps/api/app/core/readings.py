"""Readings: pure reads of a message, done off the event loop and kept for the turn.

Subject detection and the maths, physics and chemistry readers are pure functions of
the text, CPU-bound, and unbounded on a hostile message: maths parses with SymPy, and
physics and chemistry run hundreds of patterns. On the event loop one such message
stalled every request on the machine for minutes (code-health audit SCALE-01).

A function marked ``@reading`` keeps its result for the current turn.
``await read_off_loop(fn, ...)`` runs ``fn`` in the killable SymPy pool, records every
reading made there, and the turn replays them, so the sync callers deep in prompt
building get their answer without reading on the loop. A pool read that times out
declines the turn's readings: each then returns its ``declined`` value (no subject, no
intent), and the model answers without a verified solve.

Inside a turn whose message was read, a reading that was not (another text, another
argument) is computed on the event loop: it still runs, and logs, and the test suite
fails on it (``app/tests/loop_guard.py``, which also fails on SymPy run on the loop).
"""

from __future__ import annotations

import asyncio
import copy
import functools
import inspect
import logging
import sys
import time
from collections.abc import Callable
from contextvars import ContextVar
from types import FrameType
from typing import Any, cast

logger = logging.getLogger(__name__)

# The turn's readings, by (reading name, bound arguments). ``_DECLINED`` marks a turn whose
# pool read gave up: every reading then returns its declined value.
_DECLINED = ("__declined__",)
_MEMO: ContextVar[dict[tuple[Any, ...], Any] | None] = ContextVar("readings", default=None)
_IMMUTABLE = (str, int, float, bool, bytes, type(None), frozenset)
_COROUTINE_FLAGS = inspect.CO_COROUTINE | inspect.CO_ASYNC_GENERATOR
# Production logs a reading on the loop at most once per reading in this window.
_LOG_EVERY_SECONDS = 300.0
_last_logged: dict[str, float] = {}
# Called with the reading's name and the async function running it on the loop (tests).
on_loop_hooks: list[Callable[[str, str], None]] = []


def begin_turn() -> None:
    """Start an empty set of readings for the turn running in this context.

    Tasks the turn starts afterwards share it; the next turn starts its own.
    """
    _MEMO.set({})


def reading[F: Callable[..., Any]](*, declined: Any = None) -> Callable[[F], F]:
    """Keep this pure reader's results for the turn; ``declined`` is its no-answer value.

    ``declined`` may be a callable taking the reader's arguments. The reading keeps the
    reader's type, and an ``lru_cache`` under it keeps ``cache_clear``.
    """

    def wrap(fn: F) -> F:
        name = f"{fn.__module__}.{fn.__qualname__}"
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        def read(*args: Any, **kwargs: Any) -> Any:
            memo = _MEMO.get()
            key = _key(name, signature, args, kwargs)
            if memo is not None and key is not None:
                if key in memo:
                    return _fresh(memo[key])
                if _DECLINED in memo:
                    value = declined(*args, **kwargs) if callable(declined) else declined
                    return _fresh(value)
            if memo is not None:
                _note_if_on_loop(name)
            result = fn(*args, **kwargs)
            if memo is not None and key is not None:
                memo[key] = result
            return _fresh(result)

        # An lru_cache under the reading keeps its controls (tests clear it).
        for control in ("cache_clear", "cache_info"):
            if hasattr(fn, control):
                setattr(read, control, getattr(fn, control))
        # A function takes attributes; mypy models none.
        read._reading_key = lambda *args, **kwargs: _key(name, signature, args, kwargs)  # type: ignore[attr-defined]
        return cast(F, read)

    return wrap


def kept_reading[T](fn: Callable[..., T], *args: Any, **kwargs: Any) -> T | None:
    """The turn's kept reading of ``fn`` at these arguments, or None when it was not read.

    Never computes one: for code that may use a reading only when the pool made it (a
    money follow-up's earlier lines, ``turn_prep.money``). Outside a turn it is None.
    """
    memo = _MEMO.get()
    keyer = getattr(fn, "_reading_key", None)
    if memo is None or keyer is None:
        return None
    key = keyer(*args, **kwargs)
    if key is None or key not in memo:
        return None
    kept: T = memo[key]
    return _fresh(kept)


async def read_off_loop[T](
    fn: Callable[..., T],
    *args: Any,
    timeout: float,  # noqa: ASYNC109 - the pool implements it
    **kwargs: Any,
) -> T | None:
    """``fn(*args, **kwargs)`` in the SymPy pool, its readings kept for this turn.

    None when the pool gave up (a timeout, no free slot, or an error): the turn's
    readings are then declined, so nothing reads the message on the loop afterwards.
    """
    from app.core.sympy_executor import run_sympy

    memo = _MEMO.get()
    if memo is None:
        memo = {}
        _MEMO.set(memo)
    if _DECLINED in memo:
        return None
    keyer = getattr(fn, "_reading_key", None)
    key = keyer(*args, **kwargs) if keyer is not None else None
    if key is not None and key in memo:
        kept: T = memo[key]
        return _fresh(kept)
    seed = dict(memo)
    try:
        result: T
        result, recorded = await run_sympy(_record, fn, args, kwargs, seed, timeout=timeout)
    except Exception as exc:
        logger.warning(
            "reading %s gave up (%s); this turn reads no subject",
            getattr(fn, "__qualname__", fn),
            type(exc).__name__,
        )
        memo[_DECLINED] = True
        return None
    memo.update(recorded)
    return result


def keep_for_turn(name: str, value: Any) -> None:
    """Keep one thing the turn decided, beside its readings: what this turn's message is,
    not a reading of an argument, so its callers ask for it by name, not by text."""
    memo = _MEMO.get()
    if memo is not None:
        memo[("__turn__", name)] = value


def kept_for_turn(name: str) -> Any:
    """What ``keep_for_turn`` kept as ``name`` this turn, or None (no turn, nothing kept)."""
    memo = _MEMO.get()
    return None if memo is None else memo.get(("__turn__", name))


def readings_declined() -> bool:
    """True when this turn's pool read gave up and every reading returns its declined value."""
    memo = _MEMO.get()
    return memo is not None and _DECLINED in memo


def first_read(marker: tuple[Any, ...]) -> bool:
    """True the first time this turn asks ``marker``; a read that ran need not run again."""
    memo = _MEMO.get()
    if memo is None:
        memo = {}
        _MEMO.set(memo)
    if marker in memo:
        return False
    memo[marker] = True
    return True


def _record[T](
    fn: Callable[..., T],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    seed: dict[tuple[Any, ...], Any],
) -> tuple[T, dict[tuple[Any, ...], Any]]:
    """Run in a pool worker: call ``fn`` with the turn's readings so far; return the new ones."""
    token = _MEMO.set(dict(seed))
    try:
        result = fn(*args, **kwargs)
        recorded = _MEMO.get() or {}
        return result, {key: value for key, value in recorded.items() if key not in seed}
    finally:
        _MEMO.reset(token)


def _key(
    name: str, signature: inspect.Signature, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[Any, ...] | None:
    """The reading's arguments with defaults filled in; None when one is unhashable."""
    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError:
        return None
    bound.apply_defaults()
    key = (name, tuple(bound.arguments.items()))
    try:
        hash(key)
    except TypeError:
        return None
    return key


def _fresh[T](value: T) -> T:
    """A caller's own copy: a kept intent must not change what the next caller reads."""
    return value if isinstance(value, _IMMUTABLE) else copy.deepcopy(value)


def _note_if_on_loop(name: str) -> None:
    """A reading computed on the event loop for production code: log it (tests fail on it)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    owner = _nearest_coroutine()
    if owner is None or owner.startswith("app.tests") or not owner.startswith("app."):
        return
    for hook in on_loop_hooks:
        hook(name, owner)
    now = time.monotonic()
    if now - _last_logged.get(name, -_LOG_EVERY_SECONDS) >= _LOG_EVERY_SECONDS:
        _last_logged[name] = now
        logger.warning("reading %s ran on the event loop (from %s)", name, owner)


def _nearest_coroutine() -> str | None:
    """``module.function`` of the innermost ``async def`` on the stack: who reads on the loop."""
    frame: FrameType | None = sys._getframe(2)
    while frame is not None:
        if frame.f_code.co_flags & _COROUTINE_FLAGS:
            module: str = frame.f_globals.get("__name__", "")
            return f"{module}.{frame.f_code.co_name}"
        frame = frame.f_back
    return None
