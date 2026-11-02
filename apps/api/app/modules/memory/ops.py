"""Shared atomic-memory helpers used by repositories and services.

Lives under ``models`` so repositories do not import ``app.services``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.models.orm import Memory

ACTIVE_STATUS = "active"
MUTED_STATUS = "muted"
SUPERSEDED_STATUS = "superseded"

_DEFAULT_IMPORTANCE = {
    "profile": 0.8,
    "preference": 0.7,
    "project": 0.5,
    "fact": 0.5,
    "focus": 0.4,
}
_DECAY_DAYS = {
    "profile": 3650.0,
    "preference": 1825.0,
    "project": 180.0,
    "fact": 365.0,
    "focus": 45.0,
}
_CAP_EVICT_ORDER = ("focus", "fact", "project", "preference", "profile")
_PROTECTED_PROFILE_IMPORTANCE = 0.75
# A fact the user asked for ("remember that …", a hand edit) is stored at this
# importance and never pushed out by the active-fact cap. The memory model's own
# importance stays below it.
EXPLICIT_IMPORTANCE = 1.0
MODEL_IMPORTANCE_MAX = 0.95
_WS_RE = re.compile(r"\s+")


def normalize_memory_text(text: str) -> str:
    return _WS_RE.sub(" ", text.strip()).rstrip(".")


def memory_status(memory: Any) -> str:
    return str(getattr(memory, "status", None) or ACTIVE_STATUS)


def is_active_memory(memory: Any) -> bool:
    return memory_status(memory) == ACTIVE_STATUS


def importance_value(memory: Any) -> float:
    raw = getattr(memory, "importance", None)
    if raw is None:
        return _DEFAULT_IMPORTANCE.get(getattr(memory, "type", ""), 0.5)
    return float(raw)


def _last_confirmed(memory: Any) -> datetime | None:
    ts = getattr(memory, "last_confirmed_at", None) or getattr(memory, "updated_at", None)
    if not isinstance(ts, datetime):
        return None
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def recency_score(memory: Any, *, now: datetime | None = None) -> float:
    ts = _last_confirmed(memory)
    if ts is None:
        return 1.0
    now = now or datetime.now(UTC)
    days = max(0.0, (now - ts).total_seconds() / 86400.0)
    horizon = _DECAY_DAYS.get(getattr(memory, "type", ""), 365.0)
    return max(0.15, 1.0 - (days / (horizon * 2.0)))


def match_fact(
    facts: list[Memory],
    *,
    memory_type: str | None,
    match_text: str | None,
) -> Memory | None:
    needle = normalize_memory_text(match_text or "").lower()
    if not needle:
        return None
    candidates = [
        fact
        for fact in facts
        if is_active_memory(fact) and (memory_type is None or fact.type == memory_type)
    ]
    for fact in candidates:
        if normalize_memory_text(fact.text).lower() == needle:
            return fact
    for fact in candidates:
        body = normalize_memory_text(fact.text).lower()
        if needle in body or body in needle:
            return fact
    return None


def evict_for_cap(facts: list[Memory], cap: int) -> list[Memory]:
    """Return active facts that should be superseded to stay at ``cap``."""
    active = [fact for fact in facts if is_active_memory(fact)]
    overflow = len(active) - cap
    if overflow <= 0:
        return []
    ranked = sorted(
        active,
        key=lambda fact: (
            0 if fact.type in _CAP_EVICT_ORDER[:3] else 1,
            _CAP_EVICT_ORDER.index(fact.type) if fact.type in _CAP_EVICT_ORDER else 9,
            importance_value(fact),
            recency_score(fact),
        ),
    )
    evict: list[Memory] = []
    for fact in ranked:
        if len(evict) >= overflow:
            break
        if importance_value(fact) >= EXPLICIT_IMPORTANCE:
            continue
        if fact.type == "profile" and importance_value(fact) >= _PROTECTED_PROFILE_IMPORTANCE:
            continue
        evict.append(fact)
    return evict


def exact_fact(facts: list[Memory], text: str) -> Memory | None:
    """An active or muted fact of any type with exactly this text.

    An add matches only this: "User uses React Native" must not overwrite the
    richer "User uses React Native and FastAPI for Recall".
    """
    needle = normalize_memory_text(text).lower()
    for fact in facts:
        if memory_status(fact) in (ACTIVE_STATUS, MUTED_STATUS) and (
            normalize_memory_text(fact.text).lower() == needle
        ):
            return fact
    return None
