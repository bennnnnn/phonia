"""Time-ordered identifiers.

UUID version 7 (RFC 9562) embeds a millisecond Unix timestamp so ``ORDER BY id``
tracks creation time. Prefer this for rows whose ``id`` is a tiebreak in
``(created_at, id)`` cursors — random uuid4 makes same-timestamp siblings
reorder arbitrarily.
"""

from __future__ import annotations

import os
import threading
import time
from uuid import UUID

_lock = threading.Lock()
_last_ms = -1
_seq = 0


def uuid7() -> UUID:
    """Return a new UUID version 7 (millisecond-time-ordered).

    Within the same millisecond, a 12-bit sequence fills ``rand_a`` so rapid
    inserts from one process stay ordered. Existing uuid4 rows are unchanged.
    """
    global _last_ms, _seq
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms == _last_ms:
            _seq = (_seq + 1) & 0x0FFF
            if _seq == 0:
                # Sequence wrapped — wait for the next millisecond bucket.
                while True:
                    ms = time.time_ns() // 1_000_000
                    if ms > _last_ms:
                        break
                _last_ms = ms
                _seq = 0
        else:
            _last_ms = ms
            _seq = 0
        rand_a = _seq
        unix_ms = ms

    value = (unix_ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76
    value |= (rand_a & 0x0FFF) << 64
    value |= 0b10 << 62
    value |= rand_b
    return UUID(int=value)
