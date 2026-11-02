"""Memory documents: which document ("topic") each fact belongs to.

Facts stay atomic rows; a document is every active fact with the same topic.
"You" holds who the student is and how they like things explained. "Topics" are
the standard themes a tutor uses: what they study, what they aim for, how far
they've got, what they find hard. An "area" is one major course, project or part
of the student's life, named by the model (``area:science-fair``), with its own
title and one-line summary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

TopicGroup = Literal["you", "topics", "areas"]


@dataclass(frozen=True)
class TopicSpec:
    key: str
    group: TopicGroup
    title: str
    summary: str
    # The fact type stored for this topic: it drives prompt priority and decay.
    memory_type: str


STANDARD_TOPICS: tuple[TopicSpec, ...] = (
    TopicSpec("profile", "you", "Profile", "Who you are: grade, school, languages", "profile"),
    TopicSpec("preferences", "you", "Preferences", "How you like things explained", "preference"),
    TopicSpec("subjects", "topics", "Subjects", "What you study and at what level", "fact"),
    TopicSpec("goals", "topics", "Goals", "Exams and grades you're aiming for", "focus"),
    TopicSpec(
        "progress",
        "topics",
        "Learning progress",
        "What you're learning and how far you've got",
        "focus",
    ),
    TopicSpec(
        "struggles", "topics", "Struggles", "What you find hard and mistakes you make", "fact"
    ),
    TopicSpec(
        "interests", "topics", "Interests", "What you enjoy, for examples that click", "fact"
    ),
    TopicSpec("schedule", "topics", "Schedule", "Classes, study routines and exam dates", "fact"),
    TopicSpec("notes", "topics", "Other", "Other things worth remembering", "fact"),
)
STANDARD_BY_KEY = {spec.key: spec for spec in STANDARD_TOPICS}

AREA_PREFIX = "area:"
AREA_SLUG_MAX = 40
TOPIC_KEY_MAX = len(AREA_PREFIX) + AREA_SLUG_MAX
AREA_TITLE_MAX = 80
AREA_SUMMARY_MAX = 240
_AREA_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Where a fact saved before documents existed belongs, by its type.
TYPE_DEFAULT_TOPIC = {
    "profile": "profile",
    "preference": "preferences",
    "project": "notes",
    "fact": "notes",
    "focus": "progress",
}


def area_key(name: str) -> str | None:
    """``area:<slug>`` for an area name, or None when nothing usable is left."""
    slug = _AREA_SLUG_RE.sub("-", (name or "").casefold()).strip("-")
    slug = slug[:AREA_SLUG_MAX].strip("-")
    return f"{AREA_PREFIX}{slug}" if slug else None


def is_area(topic: str) -> bool:
    return topic.startswith(AREA_PREFIX)


def parse_topic(raw: str | None) -> str | None:
    """A standard key or ``area:<slug>``, or None when the model named no valid topic."""
    key = (raw or "").strip().casefold()
    if key in STANDARD_BY_KEY:
        return key
    if key.startswith(AREA_PREFIX):
        return area_key(key[len(AREA_PREFIX) :])
    return None


def topic_memory_type(topic: str) -> str:
    if is_area(topic):
        return "project"
    spec = STANDARD_BY_KEY.get(topic)
    return spec.memory_type if spec else "fact"


def fact_topic(memory: Any) -> str:
    """The stored topic, or the default for its type on a row not saved yet."""
    topic = getattr(memory, "topic", None)
    if topic:
        return str(topic)
    return TYPE_DEFAULT_TOPIC.get(str(getattr(memory, "type", "")), "notes")


def clean_area_text(text: str | None, *, limit: int) -> str:
    return " ".join((text or "").split())[:limit].strip()
