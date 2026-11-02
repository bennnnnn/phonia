"""The jobs one consumer holds: how many run at once, and a lease on each.

The consumer used to await a whole batch, so one slow job (a memory history
scan is about twenty LLM calls) stopped it reading anything else until the
slowest entry of the batch finished. Jobs now run as tasks, at most ``limit``
at once, and the consumer reads again whenever a slot is free.

A type registered with ``max_running`` (``queue.register``) runs at most that
many at once here. Its other entries wait without holding a slot, so a burst
of one slow type cannot hold back every other type; at most ``MAX_WAITING``
entries wait before the consumer stops reading.

Each held entry is leased. Every ``LEASE_INTERVAL_S`` one XCLAIM to this
consumer (JUSTID: no delivery is counted) resets the idle time of every held
entry, so a peer's reclaim (entries idle over 60s) never takes work that is
still running here, runs it twice, or counts its deliveries toward the poison
limit. A worker that dies stops renewing, and its entries are reclaimed.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import partial

from redis.asyncio import Redis
from redis.typing import StreamIdT

from app.core.jobs.queue import JOBS_GROUP, JOBS_STREAM, running_limit

logger = logging.getLogger("app.core.jobs")

# Well inside the 60s idle time after which a peer reclaims an entry.
LEASE_INTERVAL_S = 20.0
MAX_WAITING = 200


class InFlight:
    """Run held entries as tasks under the worker's and each type's limits."""

    def __init__(self, redis: Redis, consumer: str, limit: int) -> None:
        self._redis = redis
        self._consumer = consumer
        self._limit = max(1, limit)
        self._slots = asyncio.Semaphore(self._limit)
        self._type_slots: dict[str, asyncio.Semaphore] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._waiting = 0
        # Set whenever room may have grown: a job finished or began waiting.
        self._changed = asyncio.Event()
        self._closing = asyncio.Event()
        self._leasing: asyncio.Task[None] | None = None

    def room(self) -> int:
        """How many entries to read now: one per free slot, while few enough wait."""
        running = len(self._tasks) - self._waiting
        return max(0, min(self._limit - running, self._limit + MAX_WAITING - len(self._tasks)))

    def submit(
        self, entry_id: str, job_type: str | None, run: Callable[[], Awaitable[None]]
    ) -> bool:
        """Start ``run`` for this entry; False when the entry is already held here."""
        if entry_id in self._tasks:
            return False
        task = asyncio.create_task(self._run(job_type, run), name=f"job:{entry_id}")
        self._tasks[entry_id] = task
        task.add_done_callback(partial(self._finished, entry_id))
        if self._leasing is None or self._leasing.done():
            self._leasing = asyncio.create_task(self._lease_loop(), name="jobs:lease")
        return True

    async def wait_for_room(self, at_most_s: float) -> None:
        """Return once there is room to read, or after ``at_most_s`` seconds."""
        self._changed.clear()
        if self.room() > 0:
            return
        try:
            await asyncio.wait_for(self._changed.wait(), timeout=at_most_s)
        except TimeoutError:
            pass

    async def join(self) -> None:
        """Wait until every held job has finished."""
        while self._tasks:
            await asyncio.wait(set(self._tasks.values()))

    async def close(self) -> None:
        """Stop every held job and the lease.

        A stopped job leaves its entry pending and releases only a claim it
        took (``worker._process_one_entry``), so a live worker runs it again.
        """
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._closing.set()
        if self._leasing is not None:
            await asyncio.gather(self._leasing, return_exceptions=True)
            self._leasing = None

    async def renew_leases(self) -> None:
        """Reset the idle time of every held entry (never raises)."""
        entry_ids: list[StreamIdT] = list(self._tasks)
        if not entry_ids:
            return
        try:
            await self._redis.xclaim(
                JOBS_STREAM, JOBS_GROUP, self._consumer, 0, entry_ids, justid=True
            )
        except Exception:
            logger.debug("job lease renewal failed count=%s", len(entry_ids), exc_info=True)

    async def _run(self, job_type: str | None, run: Callable[[], Awaitable[None]]) -> None:
        gate = self._type_gate(job_type)
        if gate is not None:
            self._waiting += 1
            self._changed.set()
            try:
                await gate.acquire()
            finally:
                self._waiting -= 1
        try:
            async with self._slots:
                await run()
        finally:
            if gate is not None:
                gate.release()

    def _type_gate(self, job_type: str | None) -> asyncio.Semaphore | None:
        limit = running_limit(job_type)
        if limit is None or job_type is None:
            return None
        gate = self._type_slots.get(job_type)
        if gate is None:
            gate = self._type_slots[job_type] = asyncio.Semaphore(limit)
        return gate

    def _finished(self, entry_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(entry_id) is task:
            del self._tasks[entry_id]
        self._changed.set()
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            # A job's own failures are retried and dead-lettered inside the run;
            # this is the runner itself failing. Log it and keep consuming.
            logger.error("Job id=%s runner failed", entry_id, exc_info=error)

    async def _lease_loop(self) -> None:
        while self._tasks and not self._closing.is_set():
            try:
                await asyncio.wait_for(self._closing.wait(), timeout=LEASE_INTERVAL_S)
            except TimeoutError:
                await self.renew_leases()
