"""In-process cache whose entries expire and whose size is capped.

A plain module-level dict with a TTL check on read only drops an entry when
that same key is read again after it expired. Keys that are never read again
(a chat created once, a user who signed in once) stayed for the life of the
process, so the dict grew with every new chat and every new user. This cache
keeps entries in insertion order and prunes expired ones from the front on
every write, so its size follows recent traffic, not process lifetime.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class TtlCache[K, V]:
    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max(1, max_entries)
        # A test sets its own clock here, never ``time.monotonic`` for the whole process.
        self.clock = clock
        # Oldest first: a write moves its key to the end.
        self._entries: dict[K, tuple[float, V]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: K) -> V | None:
        hit = self._entries.get(key)
        if hit is None:
            return None
        stored_at, value = hit
        if self.clock() - stored_at > self._ttl:
            self._entries.pop(key, None)
            return None
        return value

    def put(self, key: K, value: V) -> None:
        now = self.clock()
        self._entries.pop(key, None)
        self._entries[key] = (now, value)
        self._prune(now)

    def pop(self, key: K) -> None:
        self._entries.pop(key, None)

    def drop_where(self, predicate: Callable[[V], bool]) -> None:
        for key in [key for key, (_at, value) in self._entries.items() if predicate(value)]:
            self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def _prune(self, now: float) -> None:
        entries = self._entries
        while entries:
            oldest = next(iter(entries))
            stored_at, _value = entries[oldest]
            if now - stored_at <= self._ttl and len(entries) <= self._max:
                return
            del entries[oldest]
