"""Detect day-planning / daily-priority questions."""

from __future__ import annotations

import re

# Natural "how's my day" phrasing.
_DAY_PLANNING = re.compile(
    r"\b("
    r"how(?:'s| is) my day|"
    r"how did my day go|"
    r"plan my day|help me plan my day|"
    r"what should i focus on today|"
    r"what(?:'s| is) worth focusing on|"
    r"what am i trying to get done today|"
    r"what(?:'s| is) still open(?: for me)?(?: to finish)?(?: tonight)?|"
    r"anything left tonight|"
    r"wrap up loose ends|"
    r"what should i tackle|what should i prioritize|"
    r"anything you think i should prioritize|"
    r"still up"
    r")\b",
    re.IGNORECASE,
)


def is_day_planning_question(text: str) -> bool:
    """True when the user wants a day snapshot, plan, or priorities."""
    cleaned = text.strip()
    if not cleaned:
        return False
    return bool(_DAY_PLANNING.search(cleaned))


_DAY_REFLECTION = re.compile(
    r"\b("
    r"how did my day go|"
    r"wrap up(?: loose ends| my day)?|"
    r"help me reflect|"
    r"reflect(?: on)?(?: my day)?|"
    r"wind down"
    r")\b",
    re.IGNORECASE,
)


def is_day_reflection_question(text: str) -> bool:
    """End-of-day reflection: what got done and what is still open."""
    cleaned = text.strip()
    if not cleaned:
        return False
    return bool(_DAY_REFLECTION.search(cleaned))
