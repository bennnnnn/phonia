"""The SymPy worker processes: how they start, run a job, and are reaped.

Split from ``sympy_executor`` (which schedules jobs onto them). The spawned worker
imports only this module's callables, so nothing here may import the web stack.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import multiprocessing.connection as mp_connection
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from typing import Any

logger = logging.getLogger("app.core.sympy_executor")

# Use the spawn start method so the worker doesn't inherit the parent's
# threads/locks (the API process is multi-threaded; fork() in a multi-
# threaded process can deadlock in the child). Each slot's worker is
# created once and reused, so the spawn cost (re-importing SymPy) is
# paid once per slot lifetime, not per call.
MP_CONTEXT = mp.get_context("spawn")

# How often a worker re-checks its parent pid (see exit_with_parent).
_PARENT_POLL_SECONDS = 1.0
# A submitted job usually starts within a millisecond. Polling from half a millisecond,
# backing off to 10 ms, keeps a message read on the turn's path from waiting a whole
# 10 ms poll for nothing (every pool call paid it).
_FIRST_POLL_SECONDS = 0.0005
_QUEUE_POLL_SECONDS = 0.01


async def wait_until_started(future: Future[Any], limit: float) -> bool:
    """Wait until the pool runs ``future`` (or it already finished); False after ``limit`` s."""
    deadline = time.monotonic() + limit
    delay = _FIRST_POLL_SECONDS
    while not future.running() and not future.done():
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(delay)
        delay = min(delay * 2, _QUEUE_POLL_SECONDS)
    return True


def exit_with_parent() -> None:
    """Pool initializer: end this worker as soon as its parent process dies.

    A worker blocked on its call queue never notices its parent dying.
    ``shutdown_sympy_executor`` covers a clean exit, but ``kill -9`` (what
    ``dev.sh kill-all`` sent), a crash or the OOM killer skip it, and each
    worker then ran on at about 250 MB, keeping the resource tracker and its
    semaphores alive too. The parent sentinel is a pipe whose write end only
    the parent holds, so it reads as closed the moment the parent is gone, on
    Linux and macOS alike. The parent pid is checked every second as well: a
    worker whose parent died is re-parented, so it still exits if any other
    process ever keeps that pipe's write end open (once seen on CI).
    """
    parent = mp.parent_process()
    if parent is None:
        return
    sentinel = parent.sentinel
    parent_pid = parent.pid

    def watch() -> None:
        while not mp_connection.wait([sentinel], timeout=_PARENT_POLL_SECONDS):
            if os.getppid() != parent_pid:
                break
        os._exit(0)

    threading.Thread(target=watch, name="sympy-parent-watch", daemon=True).start()


def sympy_worker[T](fn: Callable[..., T], *args: Any) -> T:
    """Top-level worker entry point — picklable so it can cross the
    subprocess boundary. Receives a picklable callable + args, runs them."""
    return fn(*args)


def reap_pool(pool: ProcessPoolExecutor) -> None:
    """Terminate a slot's worker process and close its pool (blocks up to ~1 s).

    ``shutdown(wait=False)`` returns immediately but does NOT kill running
    workers — they keep executing their current task. Terminate directly
    via the pool's ``_processes`` map (PID -> multiprocessing.Process) so a
    runaway SymPy call is actually stopped, not just orphaned.
    """
    processes = list(getattr(pool, "_processes", {}).values())
    for proc in processes:
        try:
            proc.terminate()
        except Exception:  # best-effort cleanup of a dying process
            logger.debug("proc.terminate failed during sympy slot kill", exc_info=True)
    # Reap terminated children before closing the executor queues. Merely
    # calling ``shutdown(wait=False)`` leaves multiprocessing queue
    # semaphores alive long enough for a sustained test/API workload to
    # exhaust macOS's system-wide semaphore limit (Errno 28), after which
    # otherwise valid math requests cannot start a verifier worker.
    for proc in processes:
        try:
            proc.join(timeout=0.5)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=0.5)
        except Exception:  # best-effort cleanup of a dying process
            logger.debug("proc.join failed during sympy slot kill", exc_info=True)
    try:
        pool.shutdown(wait=True, cancel_futures=True)
    except Exception:  # best-effort cleanup
        logger.debug("pool.shutdown failed during sympy slot kill", exc_info=True)
