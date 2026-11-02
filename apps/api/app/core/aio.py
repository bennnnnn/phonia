"""Await several coroutines as one: if any fails, the rest are cancelled. Or run one save
to its end though its caller is cancelled (``finish_despite_cancel``).

``asyncio.gather`` leaves the siblings of a failed branch running: a paid model
call, a search or a download keeps going after its turn already failed, and its
own error is never retrieved. Code that wants every branch to finish whatever the
others do passes ``return_exceptions=True`` to ``asyncio.gather`` and handles each
result (``app/tests/architecture/test_gather_cancels.py``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, overload

# The fixed-arity forms are typed as tuples, as typeshed types ``asyncio.gather``; like
# it, the result is a list at run time. Callers unpack it.


@overload
async def gather_or_cancel[A, B](a: Awaitable[A], b: Awaitable[B], /) -> tuple[A, B]: ...


@overload
async def gather_or_cancel[A, B, C](
    a: Awaitable[A], b: Awaitable[B], c: Awaitable[C], /
) -> tuple[A, B, C]: ...


@overload
async def gather_or_cancel[A, B, C, D](
    a: Awaitable[A], b: Awaitable[B], c: Awaitable[C], d: Awaitable[D], /
) -> tuple[A, B, C, D]: ...


@overload
async def gather_or_cancel[A, B, C, D, E](
    a: Awaitable[A], b: Awaitable[B], c: Awaitable[C], d: Awaitable[D], e: Awaitable[E], /
) -> tuple[A, B, C, D, E]: ...


@overload
async def gather_or_cancel[A, B, C, D, E, F](
    a: Awaitable[A],
    b: Awaitable[B],
    c: Awaitable[C],
    d: Awaitable[D],
    e: Awaitable[E],
    f: Awaitable[F],
    /,
) -> tuple[A, B, C, D, E, F]: ...


@overload
async def gather_or_cancel[T](*aws: Awaitable[T]) -> list[T]: ...


async def gather_or_cancel(*aws: Awaitable[Any]) -> Any:
    """Results in order; the first error cancels the others (awaited) and is raised."""
    tasks = [asyncio.ensure_future(aw) for aw in aws]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def finish_despite_cancel[T](
    work: Awaitable[T], *, then: Callable[[], None] | None = None
) -> T:
    """``work``'s result, run to its end even if this task is cancelled meanwhile.

    A save a cancel cuts in half can leave rows pointing at files the caller's cleanup then
    deletes. Once ``work`` has finished, ``then`` runs (to mark it done) and a cancel that
    arrived meanwhile is raised. A failure of ``work`` itself, its own cancellation
    included, is raised as it is, without ``then``.
    """
    task = asyncio.ensure_future(work)
    cancelled = False
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if then is not None:
        then()
    if cancelled:
        raise asyncio.CancelledError
    return result
