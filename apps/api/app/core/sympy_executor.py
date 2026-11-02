"""Bounded executor for SymPy work — isolates CPU-bound math in subprocesses
with a hard kill on timeout.

SymPy's ``solve``/``integrate``/``simplify`` are synchronous, CPU-bound, and
unbounded in runtime on pathological inputs. ``asyncio.to_thread`` on the
shared default thread pool:

1. Shares that pool with every other ``to_thread`` caller — a hung SymPy call
   starves unrelated async work.
2. Cannot be hard-killed: cancelling the await leaves the underlying thread
   running the bad SymPy call until it finishes (or forever), leaking the
   thread and its CPU.

This module provides dedicated, bounded ``ProcessPoolExecutor`` slots so SymPy work is
isolated and a runaway can be SIGTERM'd without killing siblings. Tests inject a
thread-based variant (a subprocess can't see test-local patches). How a worker starts
(``spawn``), runs a job and is reaped is ``sympy_worker_process``.
"""

from __future__ import annotations

import asyncio
import errno
import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any, TypeVar

from app.core.blocking import run_blocking
from app.core.log_context import current_log_ids
from app.core.sympy_worker_process import (
    MP_CONTEXT,
    exit_with_parent,
    reap_pool,
    sympy_worker,
    wait_until_started,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Interactive chat must not sit behind someone else's integral. Slot acquire
# is independent of the per-job solve timeout and does not kill the occupant.
DEFAULT_SYMPY_MAX_WORKERS = 3
DEFAULT_SYMPY_QUEUE_WAIT_SECONDS = 2.0
_MAX_SYMPY_WORKERS = 8
# After a slot is acquired the 1-worker pool may still be spawning (first
# SymPy import). That is not "queued behind another request" and must not
# share the 2s interactive wait.
_SPAWN_WAIT_SECONDS = 20.0
# A worker is replaced (warm before its slot frees) after this many jobs: SymPy's caches
# and the readers' filled one for days, with nothing to restart it short of a timeout.
DEFAULT_SYMPY_RECYCLE_AFTER_JOBS = 500


class WorkerBusyError(TimeoutError):
    """No worker came free within the queue wait: the pool is busy, the job did not run.

    Distinct from the job's own deadline, which kills its worker: a busy pool is worth
    retrying later, a job that ran too long is not.
    """


def _clamp_workers(max_workers: int) -> int:
    return max(1, min(max_workers, _MAX_SYMPY_WORKERS))


class BoundedSympyExecutor:
    """Abstract: run a picklable callable with a hard timeout."""

    @property
    def max_workers(self) -> int:
        """Number of isolated jobs this executor can run concurrently."""
        raise NotImplementedError

    async def run(
        self,
        fn: Callable[..., _T],
        *args: Any,
        timeout: float,  # noqa: ASYNC109 - we IMPLEMENT the timeout, not consume it
    ) -> _T:
        raise NotImplementedError

    def set_warmup(self, warmup: Callable[[], None]) -> None:
        """Remember the start-up solve; a slot that restarts runs it first."""

    def free_slots(self) -> int | None:
        """Slots idle right now (None when the executor does not know)."""
        return None

    def shutdown(self) -> None:
        pass


class ProcessPoolSympyExecutor(BoundedSympyExecutor):
    """Isolated 1-worker process pools for SymPy work.

    A shared ``ProcessPoolExecutor(max_workers=N)`` cannot hard-kill one
    runaway without terminating every in-flight sibling. Each slot is its
    own ``max_workers=1`` pool so timeout/cancel SIGTERM's only that worker.
    """

    def __init__(
        self,
        max_workers: int = DEFAULT_SYMPY_MAX_WORKERS,
        *,
        queue_wait_seconds: float = DEFAULT_SYMPY_QUEUE_WAIT_SECONDS,
        per_user: bool = True,
        recycle_after_jobs: int = DEFAULT_SYMPY_RECYCLE_AFTER_JOBS,
    ) -> None:
        self._max_workers = _clamp_workers(max_workers)
        self._recycle_after = max(1, recycle_after_jobs)
        self._jobs = [0] * self._max_workers
        self._queue_wait_seconds = queue_wait_seconds
        # One job per user at a time (below). The document pool turns it off: a turn reads
        # its own files side by side, and each parse is killed at its deadline anyway.
        self._per_user = per_user
        self._slots: list[ProcessPoolExecutor | None] = [None] * self._max_workers
        # A new worker imports SymPy and the solvers on its first job (about
        # 4s), which ate the 5s solve budget. After a timeout kills a worker,
        # its replacement runs the warmup before the next timed solve.
        self._cold = [True] * self._max_workers
        self._warmup: Callable[[], None] | None = None
        self._free: asyncio.Queue[int] | None = None
        # macOS named semaphores leak until reboot. Once ``sem_open`` returns
        # ENOSPC, every later process-pool attempt fails the same way, so the
        # latch stays for this process.
        self._in_process = False
        self._thread_pool: ThreadPoolExecutor | None = None
        # One slot per user at a time on this machine: three chats sending
        # pathological expressions held every slot, and every other STEM turn here
        # fell back to unverified. A user's next solve waits for their running one.
        self._owner_jobs: dict[str, asyncio.Future[None]] = {}
        # Jobs a cancelled caller left running, finishing under their own deadline.
        self._draining: set[asyncio.Task[None]] = set()

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def set_warmup(self, warmup: Callable[[], None]) -> None:
        self._warmup = warmup

    async def _claim_owner(self, owner: str | None, wait_s: float) -> None:
        """Wait (up to ``wait_s``) until ``owner`` has no solve running, then hold the turn."""
        if owner is None:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        while (running := self._owner_jobs.get(owner)) is not None:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise WorkerBusyError("SymPy: this user's previous solve is still running")
            await asyncio.wait_for(asyncio.shield(running), remaining)
        self._owner_jobs[owner] = loop.create_future()

    def _release_owner(self, owner: str | None) -> None:
        if owner is None:
            return
        running = self._owner_jobs.pop(owner, None)
        if running is not None and not running.done():
            running.set_result(None)

    def free_slots(self) -> int | None:
        return self._max_workers if self._free is None else self._free.qsize()

    def _free_queue(self) -> asyncio.Queue[int]:
        q = self._free
        if q is None:
            q = asyncio.Queue()
            for i in range(self._max_workers):
                q.put_nowait(i)
            self._free = q
        return q

    def _arm_in_process_fallback(self) -> None:
        """Keep verified lessons when the process pool cannot be created.

        A full POSIX semaphore table makes ``ProcessPoolExecutor`` raise
        ``OSError(ENOSPC)`` before any worker starts. Without this, a closed
        equation such as ``3x=3`` falls through to the model and is stamped
        unverified instead of the numbered Given / divide steps.
        """
        if self._in_process:
            return
        self._in_process = True
        # Extra threads so one timed-out solve, which cannot be killed, does
        # not occupy the only worker the next equation needs.
        self._thread_pool = ThreadPoolExecutor(
            max_workers=max(self._max_workers, 8),
            thread_name_prefix="sympy-fallback",
        )
        logger.warning(
            "sympy process pool cannot start (posix semaphore limit); "
            "verified math will run in-process until restart"
        )

    def _ensure_slot(self, slot: int) -> ProcessPoolExecutor:
        pool = self._slots[slot]
        if pool is None:
            try:
                pool = ProcessPoolExecutor(
                    max_workers=1,
                    mp_context=MP_CONTEXT,
                    initializer=exit_with_parent,
                )
            except OSError as exc:
                if exc.errno != errno.ENOSPC:
                    raise
                self._arm_in_process_fallback()
                raise
            self._slots[slot] = pool
            self._cold[slot] = True
        return pool

    async def _warm_slot(self, slot: int, pool: ProcessPoolExecutor) -> None:
        """Start a cold worker outside the solve's timeout."""
        warmup = self._warmup
        if warmup is None or not self._cold[slot]:
            return
        future = pool.submit(sympy_worker, warmup)
        try:
            async with asyncio.timeout(_SPAWN_WAIT_SECONDS):
                await asyncio.wrap_future(future)
        except TimeoutError as exc:
            logger.warning("sympy worker failed to warm after %.3fs", _SPAWN_WAIT_SECONDS)
            future.cancel()
            await self._kill_slot_async(slot)
            raise TimeoutError("SymPy worker failed to start") from exc
        self._cold[slot] = False

    def _kill_slot(self, slot: int) -> None:
        """Hard-kill one worker subprocess and drop that slot's pool (blocking: shutdown)."""
        pool = self._slots[slot]
        self._slots[slot] = None
        if pool is not None:
            reap_pool(pool)

    async def _kill_slot_async(self, slot: int) -> None:
        """Drop the slot's pool at once and reap its worker off the event loop.

        The joins wait up to a second for the process to exit; on the loop they
        stalled every other request on the machine.
        """
        pool = self._slots[slot]
        self._slots[slot] = None
        if pool is not None:
            await run_blocking("processes", reap_pool, pool)

    def _release_slot(self, slot: int) -> None:
        """Free ``slot``; a worker that has run its share of jobs is replaced and warmed first."""
        self._jobs[slot] += 1
        if self._jobs[slot] < self._recycle_after or self._slots[slot] is None:
            self._free_queue().put_nowait(slot)
            return
        self._jobs[slot] = 0

        async def replace() -> None:
            try:
                await self._kill_slot_async(slot)
                await self._warm_slot(slot, self._ensure_slot(slot))
            except Exception:  # the next job starts it cold
                logger.warning("sympy worker recycle failed", exc_info=True)
            finally:
                self._free_queue().put_nowait(slot)

        task = asyncio.get_running_loop().create_task(replace(), name="sympy_recycle")
        self._draining.add(task)
        task.add_done_callback(self._draining.discard)

    def _kill_all_slots(self) -> None:
        for i in range(self._max_workers):
            self._kill_slot(i)
        self._free = None

    async def run(
        self,
        fn: Callable[..., _T],
        *args: Any,
        timeout: float,  # noqa: ASYNC109 - we IMPLEMENT the timeout, not consume it
    ) -> _T:
        """Run ``fn`` in a worker; the worker is killed only when the solve overruns.

        A solve error (the job raised) returns the worker as it is: killing it on any
        exception made the next caller wait for a new worker's ~4 s SymPy import. A
        caller cancelled mid-solve (Stop, a closed socket) leaves the job to finish
        under its own deadline in the background, then the slot frees.
        """
        owner = current_log_ids().get("user_id") if self._per_user else None
        t_submit = time.monotonic()
        await self._claim_owner(owner, self._queue_wait_seconds)
        slot: int | None = None
        handed_off = False
        try:
            remaining_wait = max(0.0, self._queue_wait_seconds - (time.monotonic() - t_submit))
            try:
                slot = await asyncio.wait_for(self._free_queue().get(), timeout=remaining_wait)
            except TimeoutError as exc:
                logger.warning(
                    "sympy queued %.3fs without a free worker slot",
                    time.monotonic() - t_submit,
                )
                raise WorkerBusyError("SymPy worker slot wait timed out") from exc

            queue_s = time.monotonic() - t_submit
            if self._in_process:
                return await self._run_in_process(fn, args, timeout)
            try:
                pool = self._ensure_slot(slot)
            except OSError as exc:
                if exc.errno != errno.ENOSPC or not self._in_process:
                    raise
                return await self._run_in_process(fn, args, timeout)
            future = await self._start(slot, pool, fn, args)
            t_start = time.monotonic()
            try:
                async with asyncio.timeout(timeout):
                    result = await asyncio.wrap_future(future)
            except TimeoutError:
                logger.warning(
                    "sympy worker timed out after %.3fs (queued %.3fs)",
                    timeout,
                    queue_s,
                )
                future.cancel()
                await self._kill_slot_async(slot)
                raise
            except BrokenProcessPool:
                await self._kill_slot_async(slot)
                raise
            except asyncio.CancelledError:
                if not future.done():
                    handed_off = True
                    self._finish_later(slot, owner, future, deadline=t_start + timeout)
                raise
            self._cold[slot] = False
            if queue_s >= 0.05:
                logger.info(
                    "sympy queued=%.3fs ran=%.3fs",
                    queue_s,
                    time.monotonic() - t_start,
                )
            return result
        finally:
            if not handed_off:
                if slot is not None:
                    self._release_slot(slot)
                self._release_owner(owner)

    async def _start(
        self, slot: int, pool: ProcessPoolExecutor, fn: Callable[..., _T], args: tuple[Any, ...]
    ) -> Future[_T]:
        """Warm a cold worker and submit ``fn``; a worker that never starts is killed.

        A cancel in this phase also kills it: the warmup or job would otherwise run on
        in a worker the next caller expects warm.
        """
        future: Future[_T] | None = None
        try:
            if fn is not self._warmup:
                await self._warm_slot(slot, pool)
            future = pool.submit(sympy_worker, fn, *args)
            if not await wait_until_started(future, _SPAWN_WAIT_SECONDS):
                logger.warning("sympy worker failed to start after %.3fs", _SPAWN_WAIT_SECONDS)
                future.cancel()
                await self._kill_slot_async(slot)
                raise TimeoutError("SymPy worker failed to start")
            return future
        except asyncio.CancelledError:
            if future is not None:
                future.cancel()
            await self._kill_slot_async(slot)
            raise

    def _finish_later(
        self, slot: int, owner: str | None, future: Future[Any], *, deadline: float
    ) -> None:
        """Let a solve whose caller went away finish (result discarded), then free the slot.

        Killing the worker on every Stop cost the next solve a cold start. The job keeps
        its deadline: one that overruns is killed as if its caller had stayed.
        """

        async def finish() -> None:
            try:
                async with asyncio.timeout(max(0.0, deadline - time.monotonic())):
                    await asyncio.wrap_future(future)
            except TimeoutError:
                future.cancel()
                await self._kill_slot_async(slot)
            except BaseException:  # the result, or the job's error, has no caller left
                logger.debug("sympy job finished after its caller left", exc_info=True)
            finally:
                self._release_slot(slot)
                self._release_owner(owner)

        task = asyncio.get_running_loop().create_task(finish(), name="sympy_finish")
        self._draining.add(task)
        task.add_done_callback(self._draining.discard)

    async def _run_in_process(
        self,
        fn: Callable[..., _T],
        args: tuple[Any, ...],
        timeout: float,  # noqa: ASYNC109 - we IMPLEMENT the timeout, not consume it
    ) -> _T:
        pool = self._thread_pool
        if pool is None:
            raise RuntimeError("sympy in-process fallback was not armed")
        future = pool.submit(fn, *args)
        if not await wait_until_started(future, _SPAWN_WAIT_SECONDS):
            future.cancel()
            raise TimeoutError("SymPy worker failed to start")
        afut = asyncio.wrap_future(future)
        async with asyncio.timeout(timeout):
            return await afut

    def shutdown(self) -> None:
        self._kill_all_slots()
        pool = self._thread_pool
        self._thread_pool = None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)


_executor: BoundedSympyExecutor | None = None


def get_sympy_executor() -> BoundedSympyExecutor:
    global _executor
    if _executor is None:
        from app.core.config import get_settings

        settings = get_settings()
        _executor = ProcessPoolSympyExecutor(
            max_workers=settings.sympy_max_workers,
            queue_wait_seconds=settings.sympy_queue_wait_seconds,
        )
    return _executor


def set_sympy_executor(executor: BoundedSympyExecutor | None) -> None:
    """Test helper — inject a custom executor. Pass None to reset to the
    default; the previous executor is shut down."""
    global _executor
    if _executor is not None:
        _executor.shutdown()
    _executor = executor


def shutdown_sympy_executor() -> None:
    """Stop the SymPy workers when the process exits.

    A server that exits without this (``uvicorn --reload`` restarts on every
    change) left them running, about 200 MB each. Workers now also exit when
    their parent dies (``exit_with_parent``); this stops them right away.
    """
    set_sympy_executor(None)


async def warm_sympy_pool(warmup: Callable[[], None]) -> None:
    """Create every worker and import SymPy so early chats are not cold.

    ``warmup`` is a picklable, argument-free callable that runs a real solve in
    the worker; the process bootstrap passes the math module's. Warming one slot
    rotates it to the back of the free-slot queue, which made the first real
    solve select an untouched slot and pay the full spawn/import cost. Submit one
    warmup per slot concurrently so each process is ready before the API reports
    startup complete.
    """
    executor = get_sympy_executor()
    executor.set_warmup(warmup)
    # Every slot warms whatever happens to the others; a cold one warms before its first job.
    results = await asyncio.gather(
        *(executor.run(warmup, timeout=20.0) for _ in range(executor.max_workers)),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception):
            logger.warning("sympy pool warmup failed", exc_info=result)


async def run_sympy[T](
    fn: Callable[..., T],
    *args: Any,
    timeout: float,  # noqa: ASYNC109 - we IMPLEMENT the timeout, not consume it
) -> T:
    """Run a picklable callable in the bounded SymPy pool with a hard timeout.

    Raises ``TimeoutError`` if the callable does not complete within
    ``timeout`` seconds of the worker starting (the subprocess is SIGTERM'd
    in that case). Time spent waiting for a free slot does not count toward
    ``timeout`` and does not kill the occupant. Interactive slot wait is capped
    separately (default 2s) so one slow integral cannot stall ``1+1=x``.
    """
    return await get_sympy_executor().run(fn, *args, timeout=timeout)
