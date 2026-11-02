"""A periodic cycle runs about once per interval however many workers tick it.

Every worker runs every loop, out of phase. The cycle lock used to be released
as soon as a cycle finished, so a peer whose tick came later in the same
interval ran it again: M workers meant M push and email scans a minute, M
hourly retention passes and M billing reconciles.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.background import periodic
from app.core.config import Settings

_LOCK = "recall:test:lock"
_INTERVAL = 60


async def _tick(fake_redis, runs: list[str], worker: str, *, fails: bool = False) -> None:
    async def body(_settings: Settings, _lock: periodic.CycleLock) -> None:
        runs.append(worker)
        if fails:
            raise RuntimeError("cycle broke")

    with patch.object(periodic, "get_redis_client", return_value=fake_redis):
        await periodic.run_locked_cycle(
            name="test",
            lock_key=_LOCK,
            lock_ttl_seconds=periodic.lock_ttl_yield_next_tick(_INTERVAL),
            interval_seconds=_INTERVAL,
            enabled=True,
            fn=body,
            settings=Settings(),
        )


@pytest.mark.parametrize("workers", [2, 5])
async def test_run_locked_cycle_runs_once_per_interval_across_workers(fake_redis, workers):
    runs: list[str] = []
    for n in range(workers):
        await _tick(fake_redis, runs, f"w{n}")

    assert runs == ["w0"]
    assert await fake_redis.get(_LOCK) is None
    ttl = await fake_redis.ttl(periodic.ran_marker_key(_LOCK))
    assert 0 < ttl <= periodic.ran_marker_ttl(_INTERVAL)


async def test_run_locked_cycle_runs_again_once_the_marker_expires(fake_redis):
    runs: list[str] = []
    await _tick(fake_redis, runs, "w0")
    await fake_redis.delete(periodic.ran_marker_key(_LOCK))  # the interval passed
    await _tick(fake_redis, runs, "w1")

    assert runs == ["w0", "w1"]


async def test_run_locked_cycle_crashed_holder_blocks_only_until_its_lock_expires(fake_redis):
    """A holder that died mid-cycle wrote no marker: once its lock expires a peer runs."""
    runs: list[str] = []
    await fake_redis.set(_LOCK, "dead-holder", ex=periodic.lock_ttl_yield_next_tick(_INTERVAL))

    await _tick(fake_redis, runs, "w1")
    assert runs == []

    await fake_redis.delete(_LOCK)  # its TTL ran out
    await _tick(fake_redis, runs, "w1")
    assert runs == ["w1"]


async def test_run_locked_cycle_failed_cycle_counts_as_this_intervals_attempt(fake_redis):
    """One attempt per interval, as a single worker makes: peers do not retry it at once."""
    runs: list[str] = []
    await _tick(fake_redis, runs, "w0", fails=True)
    await _tick(fake_redis, runs, "w1")

    assert runs == ["w0"]
    assert await fake_redis.get(_LOCK) is None


async def test_run_locked_cycle_peer_finishing_before_the_lock_is_seen(fake_redis):
    """The marker is read again once the lock is held, in case a peer just finished."""
    runs: list[str] = []
    real_get = fake_redis.get
    reads = 0

    async def get_then_peer_finishes(key: str):
        nonlocal reads
        reads += 1
        value = await real_get(key)
        if reads == 1:
            await fake_redis.set(periodic.ran_marker_key(_LOCK), "1", ex=30)
        return value

    with patch.object(fake_redis, "get", get_then_peer_finishes):
        await _tick(fake_redis, runs, "w1")

    assert runs == []
    assert await fake_redis.exists(_LOCK) == 0


@pytest.mark.parametrize(
    "interval, ttl",
    [(1, 1), (5, 4), (60, 54), (300, 270), (3600, 3240), (0, 1)],
)
def test_ran_marker_ttl_expires_before_the_next_tick(interval, ttl):
    assert periodic.ran_marker_ttl(interval) == ttl
