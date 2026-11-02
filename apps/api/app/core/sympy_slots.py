"""Which SymPy worker slot a job may take: solves cannot fill the slot readings keep.

Every turn reads its message in the SymPy pool (``core/readings.py``, a few
milliseconds), beside real solves that may run for seconds. With one shared queue,
slow solves on every slot made each turn on the machine wait out the slot wait and
then route without its subject reading. Now solves hold at most ``slots -
reserved_for_readings`` slots at once; a reading may take any free slot, and a slot
that frees goes to a waiting reading before a waiting solve. Readings never wait
behind solves for the reserved slot, and use the solve slots when those are idle.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Literal

SympyLane = Literal["solve", "reading"]


class WorkerBusyError(TimeoutError):
    """No worker came free within the queue wait: the pool is busy, the job did not run.

    Distinct from the job's own deadline, which kills its worker: a busy pool is worth
    retrying later, a job that ran too long is not.
    """


class SlotPool:
    """Free worker slots, handed out by lane. Not thread-safe: the event loop owns it."""

    def __init__(self, slots: int, *, reserved_for_readings: int = 0) -> None:
        self._free: deque[int] = deque(range(slots))
        # Solves always keep at least one slot.
        reserved = max(0, min(reserved_for_readings, slots - 1))
        self._solve_cap = slots - reserved
        self._solves: set[int] = set()
        self._waiters: deque[tuple[SympyLane, asyncio.Future[int]]] = deque()

    def qsize(self) -> int:
        return len(self._free)

    def empty(self) -> bool:
        return not self._free

    def get_nowait(self, lane: SympyLane = "reading") -> int:
        if not self._free or not self._may_take(lane):
            raise asyncio.QueueEmpty
        return self._take(lane)

    async def get(self, lane: SympyLane = "reading") -> int:
        """A slot for ``lane`` (any slot by default), waiting (cancellable) for one."""
        # A waiter that could take a free slot was handed it when the slot freed, so
        # a slot free now is one no waiter of this lane is owed.
        if self._free and self._may_take(lane):
            return self._take(lane)
        waiter: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        entry = (lane, waiter)
        self._waiters.append(entry)
        try:
            return await waiter
        except asyncio.CancelledError:
            if waiter.done() and not waiter.cancelled():
                self.put_nowait(waiter.result())  # handed a slot as the wait ended
            elif entry in self._waiters:
                self._waiters.remove(entry)
            raise

    def put_nowait(self, slot: int) -> None:
        self._solves.discard(slot)
        self._free.append(slot)
        self._hand_out()

    def _may_take(self, lane: SympyLane) -> bool:
        return lane == "reading" or len(self._solves) < self._solve_cap

    def _take(self, lane: SympyLane) -> int:
        slot = self._free.popleft()
        if lane == "solve":
            self._solves.add(slot)
        return slot

    def _hand_out(self) -> None:
        """Give free slots to waiters: readings first, then solves while under their cap."""
        while self._free:
            entry = self._next_waiter()
            if entry is None:
                return
            self._waiters.remove(entry)
            lane, waiter = entry
            waiter.set_result(self._take(lane))

    def _next_waiter(self) -> tuple[SympyLane, asyncio.Future[int]] | None:
        for entry in [e for e in self._waiters if e[1].done()]:
            self._waiters.remove(entry)
        reading = next((e for e in self._waiters if e[0] == "reading"), None)
        if reading is not None:
            return reading
        if self._may_take("solve"):
            return next(iter(self._waiters), None)
        return None


class OwnerTurns:
    """One running job per owner (a user and a lane) on this machine.

    Three chats sending pathological expressions held every slot, and every other STEM
    turn here fell back to unverified. A user's next solve waits for their running one;
    their reading has its own turn, so it never waits behind their solve.
    """

    def __init__(self) -> None:
        self.running: dict[str, asyncio.Future[None]] = {}

    async def claim(self, owner: str | None, wait_s: float) -> None:
        """Wait (up to ``wait_s``) until ``owner`` has no job running, then hold the turn."""
        if owner is None:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        while (running := self.running.get(owner)) is not None:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise WorkerBusyError("SymPy: this user's previous solve is still running")
            await asyncio.wait_for(asyncio.shield(running), remaining)
        self.running[owner] = loop.create_future()

    def release(self, owner: str | None) -> None:
        if owner is None:
            return
        running = self.running.pop(owner, None)
        if running is not None and not running.done():
            running.set_result(None)
