"""Atomic memory scoring and prompt packing — no IO."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.models.orm import Memory
from app.modules.memory.ops import (
    ACTIVE_STATUS as ACTIVE_STATUS,
)
from app.modules.memory.ops import (
    MUTED_STATUS as MUTED_STATUS,
)
from app.modules.memory.ops import (
    SUPERSEDED_STATUS as SUPERSEDED_STATUS,
)
from app.modules.memory.ops import (
    evict_for_cap as evict_for_cap,
)
from app.modules.memory.ops import (
    importance_value,
    normalize_memory_text,
    recency_score,
)
from app.modules.memory.ops import (
    is_active_memory as is_active_memory,
)
from app.modules.memory.ops import (
    match_fact as match_fact,
)
from app.modules.memory.ops import (
    memory_status as memory_status,
)
from app.modules.memory.text import (
    classify_memory_sensitivity,
    is_food_or_diet_memory_text,
    is_sensitive_memory_text,
)
from app.modules.memory.user_name import names_another_person, names_the_user

TYPE_PRIORITY = {"profile": 0, "preference": 1, "project": 2, "fact": 3, "focus": 4}
SECTION_LABELS = {
    "profile": "Profile",
    "preference": "Preferences",
    "project": "Projects",
    "fact": "Facts",
    "focus": "Focus",
}

# Always in the prompt: who the user is by name, and how they want replies.
# Their job, city and the rest are only there when the turn is about them.
_IDENTITY_NAME_LIMIT = 1
_IDENTITY_PREF_LIMIT = 4
_LOW_CONFIDENCE = 0.6
_NEVER = datetime.min.replace(tzinfo=UTC)


def fallback_score(memory: Any) -> float:
    type_prior = 1.0 - (TYPE_PRIORITY.get(getattr(memory, "type", ""), 9) * 0.05)
    return (importance_value(memory) * 0.55) + (recency_score(memory) * 0.3) + (type_prior * 0.15)


def semantic_score(memory: Any, cosine: float) -> float:
    type_prior = 1.0 - (TYPE_PRIORITY.get(getattr(memory, "type", ""), 9) * 0.05)
    return (
        (cosine * 0.55)
        + (importance_value(memory) * 0.25)
        + (recency_score(memory) * 0.15)
        + (type_prior * 0.05)
    )


def is_communication_preference(memory: Any) -> bool:
    """How the user wants replies or lessons ("keep lists under five things").

    The preferences document holds only these; an older food preference ("prefers
    oat milk") is a fact for food questions, not for every reply.
    """
    if getattr(memory, "type", "") != "preference":
        return False
    return not is_food_or_diet_memory_text(str(getattr(memory, "text", "") or ""))


def is_name_fact(memory: Any) -> bool:
    """ "User's name is Bini", "User goes by Ben": the profile fact every reply may use.

    "User's sister's name is Sam" names someone else and is not one.
    """
    if getattr(memory, "type", "") != "profile":
        return False
    return names_the_user(normalize_memory_text(getattr(memory, "text", "")))


def identity_core(memories: list[Memory], *, profile_name: str | None = None) -> list[Memory]:
    """The user's name and their communication preferences: on every memory turn.

    The name is the newest fact that names the user ("call me Ben" after "I'm Bini"),
    never one that names them differently from ``profile_name`` (``user_name``).
    """
    names = [
        m
        for m in memories
        if is_name_fact(m) and not names_another_person(str(m.text), profile_name)
    ]
    names.sort(key=lambda m: (said_at(m), importance_value(m)), reverse=True)
    prefs = [m for m in memories if is_communication_preference(m)]
    prefs.sort(key=lambda m: (importance_value(m), recency_score(m)), reverse=True)
    return [*names[:_IDENTITY_NAME_LIMIT], *prefs[:_IDENTITY_PREF_LIMIT]]


def should_skip_sensitive_persist(
    *,
    sensitivity: str,
    text: str,
    explicit_remember: bool,
    include_sensitive: bool,
) -> bool:
    classified = sensitivity or classify_memory_sensitivity(text)
    if include_sensitive or explicit_remember:
        return False
    if classified != "normal":
        return True
    return is_sensitive_memory_text(text)


def render_memory_block(memories: list[Any]) -> str:
    if not memories:
        return ""
    ordered = sorted(memories, key=lambda m: TYPE_PRIORITY.get(m.type, 99))
    lines = ["Known facts about the user:"]
    current_type: str | None = None
    for memory in ordered:
        if memory.type != current_type:
            label = SECTION_LABELS.get(memory.type, str(memory.type).title())
            lines.append(f"\n## {label}")
            current_type = memory.type
        lines.append(_fact_line(memory))
    return "\n".join(lines)


def said_at(memory: Any) -> datetime:
    """When the user last said this fact; the earliest time when the row has none."""
    said = getattr(memory, "last_confirmed_at", None) or getattr(memory, "created_at", None)
    if not isinstance(said, datetime):
        return _NEVER
    return said if said.tzinfo is not None else said.replace(tzinfo=UTC)


def _fact_line(memory: Any) -> str:
    """ "- User works at Stripe (said 2026-05)": when it was said, and if it is unsure."""
    notes: list[str] = []
    said = getattr(memory, "last_confirmed_at", None) or getattr(memory, "created_at", None)
    if isinstance(said, datetime):
        notes.append(f"said {said:%Y-%m}")
    confidence = getattr(memory, "confidence", None)
    if isinstance(confidence, int | float | Decimal) and float(confidence) < _LOW_CONFIDENCE:
        notes.append("unconfirmed")
    text = str(memory.text).strip()
    return f"- {text} ({', '.join(notes)})" if notes else f"- {text}"


def pack_memories(memories: list[Any], *, max_chars: int) -> list[Any]:
    if max_chars <= 0:
        return list(memories)
    packed: list[Any] = []
    for memory in memories:
        trial = [*packed, memory]
        if len(render_memory_block(trial)) > max_chars:
            continue
        packed.append(memory)
    return packed
