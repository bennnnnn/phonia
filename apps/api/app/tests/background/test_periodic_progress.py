"""A long scheduler cycle that is making progress does not read as dead.

The loop heartbeat was touched only between cycles, so the worker's
``/health/ready`` failed (503) whenever one cycle ran past 120s. The billing
reconcile cycle makes one RevenueCat call plus a 0.2s gap per Pro user, so a
few hundred Pro users (or a slow RevenueCat) was enough. A cycle that stops
making progress must still go stale.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from app.background import periodic
from app.core.config import Settings

_STALE_S = 0.15


class _Redis:
    """Just enough of Redis for acquire/refresh/release of one lock."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, _script: str, _numkeys: int, key: str, token: str, *_args: Any) -> int:
        return 1 if self.values.get(key) == token else 0

    async def get(self, key: str) -> str | None:
        return self.values.get(key)


@pytest.mark.parametrize("makes_progress, alive_during_cycle", [(True, True), (False, False)])
async def test_cycle_progress_keeps_the_loop_alive(
    makes_progress: bool, alive_during_cycle: bool
) -> None:
    name = f"progress-{makes_progress}"
    finished = asyncio.Event()

    async def body(_settings: Settings, lock: periodic.CycleLock) -> None:
        for _ in range(8):
            await asyncio.sleep(0.05)
            if makes_progress:
                assert await lock.refresh()
        finished.set()

    async def cycle(settings: Settings) -> None:
        await periodic.run_locked_cycle(
            name=name,
            lock_key=f"lock:{name}",
            lock_ttl_seconds=60,
            enabled=True,
            fn=body,
            settings=settings,
        )

    samples: list[bool] = []
    with (
        patch.object(periodic, "_HEARTBEAT_STALE_THRESHOLD_S", _STALE_S),
        patch.object(periodic, "get_redis_client", return_value=_Redis()),
    ):
        await periodic.start_periodic(
            name=name, interval_seconds=3600, enabled=True, cycle=cycle, settings=Settings()
        )
        try:
            while not finished.is_set():
                await asyncio.sleep(0.03)
                samples.append(periodic.is_periodic_alive(name))
        finally:
            await periodic.stop_periodic(name)
    # The cycle runs ~0.4s, well past the 0.15s stale threshold.
    assert samples
    assert all(samples) is alive_during_cycle
