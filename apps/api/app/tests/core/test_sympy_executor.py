"""Tests for the bounded SymPy subprocess executor.

These exercise the production ``ProcessPoolSympyExecutor`` directly (not via
the adapter/tools layer, which uses the injectable ``thread_sympy_executor``
fixture for monkeypatch-friendly tests). They use top-level picklable
functions so the callables can cross the subprocess boundary.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.core.sympy_executor import (
    BoundedSympyExecutor,
    ProcessPoolSympyExecutor,
    run_sympy,
    set_sympy_executor,
    warm_sympy_pool,
)
from app.modules.math.sympy_warmup import warm_math_worker
from app.tests.sympy_support import ThreadSympyExecutor


def _sleep(seconds: float) -> int:
    time.sleep(seconds)
    return 1


def _divide(a: int, b: int) -> float:
    return a / b


def _add(a: int, b: int) -> int:
    """Picklable top-level function — the subprocess resolves it by qualified
    name from the forked ``sys.modules``."""
    return a + b


def _sleep_forever(_ignored: object = None) -> int:
    """Hangs forever — used to verify the hard-kill-on-timeout path. Returns
    the PID so a test could (if needed) confirm the PID is gone after kill."""
    time.sleep(30)
    return 0


def _echo_pid() -> int:
    import os

    return os.getpid()


_WARMED = False


def _slow_warmup() -> None:
    """Stands in for the first-job SymPy import: slow, and once per worker."""
    global _WARMED
    time.sleep(1.5)
    _WARMED = True


def _was_warmed() -> bool:
    return _WARMED


class _WarmupProbeExecutor(BoundedSympyExecutor):
    def __init__(self, max_workers: int) -> None:
        self._max_workers = max_workers
        self.calls = 0
        self.active = 0
        self.peak_active = 0

    @property
    def max_workers(self) -> int:
        return self._max_workers

    async def run(self, fn, *args, timeout: float):  # noqa: ASYNC109 - protocol implementation
        self.calls += 1
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        await asyncio.sleep(0.01)
        result = fn(*args)
        self.active -= 1
        return result


@pytest.mark.asyncio
async def test_semaphore_exhaustion_still_runs_the_solve():
    """A full POSIX semaphore table must not drop a verified equation lesson.

    ``3x=3`` used to fall through to the model plus the unverified note
    because ``ProcessPoolExecutor`` raised ``ENOSPC`` before a worker existed.
    """
    import errno
    import os

    constructions = 0

    class _NoSemaphores:
        def __init__(self, *args: object, **kwargs: object) -> None:
            nonlocal constructions
            constructions += 1
            raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.core.sympy_executor.ProcessPoolExecutor", _NoSemaphores)
    executor = ProcessPoolSympyExecutor(max_workers=1)
    set_sympy_executor(executor)
    try:
        assert await run_sympy(_add, 2, 3, timeout=5) == 5
        assert await run_sympy(_echo_pid, timeout=5) == os.getpid()
        assert constructions == 1
    finally:
        monkeypatch.undo()
        set_sympy_executor(None)


@pytest.mark.asyncio
async def test_run_sympy_returns_result():
    """A simple picklable callable runs in the subprocess and returns its
    result."""
    set_sympy_executor(ProcessPoolSympyExecutor(max_workers=1))
    result = await run_sympy(_add, 2, 3, timeout=10)
    assert result == 5


@pytest.mark.asyncio
async def test_run_sympy_runs_in_subprocess():
    """The callable runs in a different process (not the pytest parent)."""
    import os

    set_sympy_executor(ProcessPoolSympyExecutor(max_workers=1))
    worker_pid = await run_sympy(_echo_pid, timeout=10)
    assert worker_pid != os.getpid()


@pytest.mark.asyncio
async def test_default_uses_isolated_one_worker_slots():
    """Default is several isolated 1-worker pools, not one shared N-worker
    pool (killing that would SIGTERM every in-flight sibling)."""
    executor = ProcessPoolSympyExecutor()
    assert executor._max_workers == 3
    pool = executor._ensure_slot(0)
    assert pool._max_workers == 1
    executor.shutdown()


@pytest.mark.asyncio
async def test_warmup_starts_every_worker_slot_concurrently():
    executor = _WarmupProbeExecutor(max_workers=3)
    set_sympy_executor(executor)

    await warm_sympy_pool(warm_math_worker)

    assert executor.calls == 3
    assert executor.peak_active == 3


@pytest.mark.asyncio
async def test_pool_size_bounded_to_one_worker():
    """A slot is always max_workers=1 — a runaway occupies that subprocess
    only. The executor must not grow unbounded (DoS protection)."""
    executor = ProcessPoolSympyExecutor(max_workers=1)
    assert executor._max_workers == 1
    pool = executor._ensure_slot(0)
    assert pool._max_workers == 1
    executor.shutdown()


@pytest.mark.asyncio
async def test_timeout_raises_and_kills_worker():
    """On timeout, ``TimeoutError`` is raised quickly AND the worker is
    SIGTERM'd (not just orphaned). We verify the kill by checking that a
    subsequent call returns a DIFFERENT worker PID (the pool was recreated
    with a fresh worker because the old one was killed)."""
    executor = ProcessPoolSympyExecutor(max_workers=1)
    set_sympy_executor(executor)
    try:
        first_pid = await run_sympy(_echo_pid, timeout=10)
        with pytest.raises(TimeoutError):
            await run_sympy(_sleep_forever, None, timeout=0.5)
        # The pool was killed and recreated; the new worker has a different PID.
        second_pid = await run_sympy(_echo_pid, timeout=10)
        assert second_pid != first_pid
    finally:
        executor.shutdown()


@pytest.mark.asyncio
async def test_restarted_worker_warms_outside_the_solve_timeout():
    """A worker killed by a timeout comes back cold. Its first solve used to
    pay the SymPy import inside a 5s budget and time out too, so the next
    question after a slow one went unverified."""
    executor = ProcessPoolSympyExecutor(max_workers=1)
    executor.set_warmup(_slow_warmup)
    set_sympy_executor(executor)
    try:
        assert await run_sympy(_was_warmed, timeout=1.0) is True
        with pytest.raises(TimeoutError):
            await run_sympy(_sleep_forever, None, timeout=0.5)
        assert await run_sympy(_was_warmed, timeout=1.0) is True
    finally:
        executor.shutdown()


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_timeout_returns_quickly():
    """The timeout must fire at the configured deadline, not wait for the
    runaway callable to finish (which would defeat the DoS protection)."""
    set_sympy_executor(ProcessPoolSympyExecutor(max_workers=1))
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await run_sympy(_sleep_forever, None, timeout=0.3)
    elapsed = time.monotonic() - started
    # Allow generous slack for process startup + scheduling, but it must NOT
    # wait the full 30s sleep.
    assert elapsed < 5.0


@pytest.mark.asyncio
async def test_a_cancelled_solve_finishes_and_keeps_its_warm_worker():
    """A caller's cancel (Stop, a closed socket) no longer kills the worker: the job runs
    to its end, then the slot frees, and the next solve is not a cold start."""
    executor = ProcessPoolSympyExecutor(max_workers=1)
    set_sympy_executor(executor)
    try:
        first_pid = await run_sympy(_echo_pid, timeout=10)
        task = asyncio.create_task(run_sympy(_sleep, 0.5, timeout=30))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        second_pid = await run_sympy(_echo_pid, timeout=10)
        assert second_pid == first_pid
    finally:
        executor.shutdown()


@pytest.mark.asyncio
async def test_a_cancelled_solve_past_its_deadline_is_still_killed():
    executor = ProcessPoolSympyExecutor(max_workers=1)
    set_sympy_executor(executor)
    try:
        first_pid = await run_sympy(_echo_pid, timeout=10)
        task = asyncio.create_task(run_sympy(_sleep_forever, None, timeout=1.0))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        second_pid = await run_sympy(_echo_pid, timeout=10)
        assert second_pid != first_pid
    finally:
        executor.shutdown()


@pytest.mark.asyncio
async def test_a_solve_error_keeps_the_worker():
    """A job that raises leaves a healthy worker: killing it cost a ~4 s cold start."""
    executor = ProcessPoolSympyExecutor(max_workers=1)
    set_sympy_executor(executor)
    try:
        first_pid = await run_sympy(_echo_pid, timeout=10)
        with pytest.raises(ZeroDivisionError):
            await run_sympy(_divide, 1, 0, timeout=10)
        assert await run_sympy(_echo_pid, timeout=10) == first_pid
    finally:
        executor.shutdown()


@pytest.mark.asyncio
async def test_a_worker_is_replaced_after_its_share_of_jobs():
    """A long-lived worker's caches grew for days: after N jobs it is swapped for a new one."""
    executor = ProcessPoolSympyExecutor(max_workers=1, recycle_after_jobs=2)
    set_sympy_executor(executor)
    try:
        first = await run_sympy(_echo_pid, timeout=10)
        assert await run_sympy(_echo_pid, timeout=10) == first
        # The second job was the worker's last: the next one runs in its replacement.
        third = await run_sympy(_echo_pid, timeout=20)
        assert third != first
        assert await run_sympy(_echo_pid, timeout=10) == third
    finally:
        executor.shutdown()


@pytest.mark.asyncio
async def test_a_spent_slot_is_replaced_and_warmed_before_it_frees():
    """The recycle path alone, with no processes (a full semaphore table runs in-process)."""
    executor = ProcessPoolSympyExecutor(max_workers=1, recycle_after_jobs=2)
    calls: list[str] = []
    old_pool, new_pool = object(), object()
    executor._slots[0] = old_pool

    async def kill(slot: int) -> None:
        calls.append("kill")
        executor._slots[slot] = None

    def ensure(slot: int) -> object:
        calls.append("ensure")
        executor._slots[slot] = new_pool
        return new_pool

    async def warm(slot: int, pool: object) -> None:
        calls.append("warm")
        assert pool is new_pool

    executor._kill_slot_async = kill
    executor._ensure_slot = ensure
    executor._warm_slot = warm
    free = executor._free_queue()
    await free.get()

    executor._release_slot(0)
    assert free.qsize() == 1 and calls == []
    await free.get()
    executor._release_slot(0)
    # The second job was the worker's last: the slot frees only once its replacement is warm.
    assert free.qsize() == 0
    await asyncio.gather(*executor._draining)
    assert calls == ["kill", "ensure", "warm"]
    assert free.qsize() == 1
    assert executor._jobs == [0]


@pytest.mark.asyncio
async def test_concurrent_call_queued_behind_single_worker():
    """max_workers=1 means a second call queues behind the first. This
    verifies the bound — SymPy can't run N concurrent solves and exhaust the
    CPU. (Not a hard-kill test; a behavioral check on the bound.)"""
    set_sympy_executor(ProcessPoolSympyExecutor(max_workers=1))

    async def _slow_add() -> int:
        return await run_sympy(_add, 1, 2, timeout=10)

    # Submit two calls concurrently; with max_workers=1 they serialize.
    results = await asyncio.gather(_slow_add(), _slow_add())
    assert results == [3, 3]


@pytest.mark.asyncio
async def test_timeout_excludes_queue_wait():
    """The solve timeout starts when the worker runs, not when the call is
    submitted — a queued call must not time out (and kill the occupant)
    just because it waited for the single slot.

    Uses the thread executor so occupancy is deterministic (no spawn delay).
    """
    executor = ThreadSympyExecutor(max_workers=1)
    set_sympy_executor(executor)
    try:
        occupier = asyncio.create_task(run_sympy(_sleep, 0.4, timeout=5))
        await asyncio.sleep(0.05)
        result = await run_sympy(_add, 2, 3, timeout=0.15)
        assert result == 5
        assert await occupier == 1
    finally:
        executor.shutdown()


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_queue_wait_fails_closed_without_killing_occupant():
    """Interactive math must not wait 60s for a busy slot — fail closed so
    the turn can fall back to unverified prose."""
    executor = ThreadSympyExecutor(max_workers=1, queue_wait_seconds=0.12)
    set_sympy_executor(executor)
    try:
        occupier = asyncio.create_task(run_sympy(_sleep, 0.8, timeout=5))
        await asyncio.sleep(0.05)
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="slot wait"):
            await run_sympy(_add, 2, 3, timeout=5)
        assert time.monotonic() - started < 0.5
        assert await occupier == 1
    finally:
        executor.shutdown()


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_two_workers_run_in_parallel():
    """Two slots must overlap; they must not serialize behind one 5s budget."""
    executor = ThreadSympyExecutor(max_workers=2, queue_wait_seconds=2.0)
    set_sympy_executor(executor)
    try:
        started = time.monotonic()
        results = await asyncio.gather(
            run_sympy(_sleep, 0.4, timeout=5),
            run_sympy(_sleep, 0.4, timeout=5),
        )
        elapsed = time.monotonic() - started
        assert results == [1, 1]
        assert elapsed < 0.75
    finally:
        executor.shutdown()


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_timeout_does_not_kill_sibling_slot():
    """A timeout on one slot must not BrokenProcessPool a sibling solve."""
    executor = ProcessPoolSympyExecutor(max_workers=2, queue_wait_seconds=2.0)
    set_sympy_executor(executor)
    try:
        occupier = asyncio.create_task(run_sympy(_sleep_forever, None, timeout=8))
        await asyncio.sleep(1.0)
        started = time.monotonic()
        result = await run_sympy(_add, 2, 3, timeout=10)
        assert result == 5
        assert time.monotonic() - started < 6.0
        occupier.cancel()
        with pytest.raises((TimeoutError, asyncio.CancelledError)):
            await occupier
        assert await run_sympy(_add, 4, 1, timeout=10) == 5
    finally:
        executor.shutdown()


_PARENT_SCRIPT = """
import asyncio, os
from app.core.sympy_executor import ProcessPoolSympyExecutor

async def main():
    executor = ProcessPoolSympyExecutor(max_workers=2)
    pids = await asyncio.gather(*(executor.run(os.getpid, timeout=30) for _ in range(2)))
    print(" ".join(map(str, pids)), flush=True)
    await asyncio.sleep(120)

asyncio.run(main())
"""


def _alive(pid: int) -> bool:
    """True for a running process; a zombie waiting to be reaped counts as gone."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = Path(f"/proc/{pid}/stat")
    try:
        return stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        # No /proc (macOS): the signal probe above is all there is.
        return not stat.parent.parent.exists()


@pytest.mark.parametrize(
    "sig",
    [pytest.param(signal.SIGKILL, id="SIGKILL"), pytest.param(signal.SIGTERM, id="SIGTERM")],
)
def test_workers_exit_when_the_parent_dies_without_cleanup(sig: signal.Signals):
    """A killed API must not leave its SymPy workers running.

    ``shutdown_sympy_executor`` runs only on a clean exit. ``dev.sh kill-all``
    (``kill -9``), a crash or the OOM killer skip it, and a pool worker blocked
    on its call queue never noticed: each one stayed at about 250 MB.
    """
    parent = subprocess.Popen(  # noqa: S603 - fixed argv: this interpreter and a literal script
        [sys.executable, "-c", _PARENT_SCRIPT],
        cwd=Path(__file__).resolve().parents[3],
        stdout=subprocess.PIPE,
        text=True,
    )
    worker_pids: list[int] = []
    try:
        assert parent.stdout is not None
        ready, _, _ = select.select([parent.stdout], [], [], 60)
        assert ready, "the parent never started its workers"
        worker_pids = [int(pid) for pid in parent.stdout.readline().split()]
        assert len(set(worker_pids)) == 2
        assert all(_alive(pid) for pid in worker_pids)

        parent.send_signal(sig)
        parent.wait(timeout=10)

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(_alive(pid) for pid in worker_pids):
            time.sleep(0.1)
        assert [pid for pid in worker_pids if _alive(pid)] == []
    finally:
        for pid in worker_pids:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)
        if parent.poll() is None:
            parent.kill()
            parent.wait()


_HELD_PIPE_SCRIPT = """
import multiprocessing, os, time
from types import SimpleNamespace
from app.core import sympy_worker_process

# The parent pipe stays open (this process holds its write end), but the
# recorded parent pid is not ours: the backstop must still end the worker.
read_end, write_end = os.pipe()
multiprocessing.parent_process = lambda: SimpleNamespace(sentinel=read_end, pid=os.getppid() + 1)
sympy_worker_process.mp.parent_process = multiprocessing.parent_process
sympy_worker_process.exit_with_parent()
time.sleep(30)
raise SystemExit(3)
"""


@pytest.mark.wall_clock
def test_worker_exits_when_its_parent_pid_changes_even_if_the_pipe_stays_open():
    """Backstop for the parent pipe: a re-parented worker exits within ~1 s."""
    started = time.monotonic()
    result = subprocess.run(  # noqa: S603 - fixed argv: this interpreter and a literal script
        [sys.executable, "-c", _HELD_PIPE_SCRIPT],
        cwd=Path(__file__).resolve().parents[3],
        timeout=20,
        check=False,
    )
    assert result.returncode == 0
    assert time.monotonic() - started < 15
