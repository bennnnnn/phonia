"""What ``repository.list_scored_for_user`` returns, for facts built in memory.

Recall ranks in SQL now. A test gives a fact its stored vector with ``embedding_json``
(a transient row keeps it) and this pairs each fact with the cosine similarity Postgres
would compute against ``query``, or None for a fact with no vector.
"""

from __future__ import annotations

import json
import math
from typing import Any


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norms if norms else 0.0


def scored(memories: list[Any], query: list[float]) -> list[tuple[Any, float | None]]:
    pairs: list[tuple[Any, float | None]] = []
    for memory in memories:
        raw = vars(memory).get("embedding_json") if hasattr(memory, "__dict__") else None
        vector = json.loads(raw) if raw else None
        pairs.append((memory, None if vector is None else cosine(query, vector)))
    return pairs


def scored_reader(memories: list[Any]) -> Any:
    """A stand-in for ``list_scored_for_user`` over ``memories``."""

    async def read(_session: Any, _user_id: Any, query: list[float]) -> list[Any]:
        return scored(memories, query)

    return read
