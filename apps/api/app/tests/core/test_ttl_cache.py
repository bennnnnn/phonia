"""Tests for the bounded in-process TTL cache."""

from __future__ import annotations

import pytest

from app.core.ttl_cache import TtlCache


@pytest.fixture
def clock() -> list[float]:
    return [1_000.0]


@pytest.mark.parametrize(
    "age, expected",
    [(0.0, "v"), (9.9, "v"), (10.0, "v"), (10.1, None), (500.0, None)],
)
def test_ttl_cache_get_respects_ttl(clock: list[float], age: float, expected: str | None):
    cache: TtlCache[str, str] = TtlCache(ttl_seconds=10, max_entries=10, clock=lambda: clock[0])
    cache.put("k", "v")
    clock[0] += age
    assert cache.get("k") == expected


@pytest.mark.parametrize(
    "writes, gap, expected_len",
    [
        (5, 0.0, 5),  # all fresh
        (5, 11.0, 1),  # each write expires everything before it
        (5, 4.0, 3),  # a window of ~10s holds three writes 4s apart
    ],
)
def test_ttl_cache_put_prunes_entries_nobody_reads(
    clock: list[float], writes: int, gap: float, expected_len: int
):
    cache: TtlCache[int, int] = TtlCache(ttl_seconds=10, max_entries=100, clock=lambda: clock[0])
    for i in range(writes):
        cache.put(i, i)
        clock[0] += gap
    assert len(cache) == expected_len


@pytest.mark.parametrize("max_entries, writes", [(1, 5), (3, 10), (10, 10)])
def test_ttl_cache_caps_entries_evicting_oldest(clock: list[float], max_entries: int, writes: int):
    cache: TtlCache[int, int] = TtlCache(
        ttl_seconds=60, max_entries=max_entries, clock=lambda: clock[0]
    )
    for i in range(writes):
        cache.put(i, i)
    assert len(cache) == min(max_entries, writes)
    assert cache.get(writes - 1) == writes - 1
    if writes > max_entries:
        assert cache.get(0) is None


def test_ttl_cache_rewrite_refreshes_age_and_order(clock: list[float]):
    cache: TtlCache[str, int] = TtlCache(ttl_seconds=10, max_entries=2, clock=lambda: clock[0])
    cache.put("a", 1)
    clock[0] += 8
    cache.put("b", 2)
    cache.put("a", 3)  # newest again
    clock[0] += 5
    cache.put("c", 4)  # cap 2: evicts the oldest, now "b"
    assert cache.get("a") == 3
    assert cache.get("b") is None
    assert cache.get("c") == 4


def test_ttl_cache_pop_and_drop_where(clock: list[float]):
    cache: TtlCache[int, str] = TtlCache(ttl_seconds=10, max_entries=10, clock=lambda: clock[0])
    for i, owner in enumerate(["ann", "bob", "ann", "cy"]):
        cache.put(i, owner)
    cache.pop(3)
    cache.pop(99)
    cache.drop_where(lambda owner: owner == "ann")
    assert len(cache) == 1
    assert cache.get(1) == "bob"
    cache.clear()
    assert len(cache) == 0
