from types import SimpleNamespace

import pytest

from app.modules.memory.topics import (
    STANDARD_TOPICS,
    TYPE_DEFAULT_TOPIC,
    area_key,
    fact_topic,
    parse_topic,
    topic_memory_type,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("subjects", "subjects"),
        ("tech-stack", None),
        ("side-projects", None),
        ("recent-work", None),
        ("  Preferences ", "preferences"),
        ("area:recall", "area:recall"),
        ("area:My Big App!", "area:my-big-app"),
        ("area:", None),
        ("area:!!!", None),
        ("hobbies", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_topic_accepts_standard_keys_and_areas_only(raw, expected):
    assert parse_topic(raw) == expected


def test_area_key_slugs_and_caps_the_name():
    assert area_key("Africana — diaspora app") == "area:africana-diaspora-app"
    long_key = area_key("x" * 100)
    assert long_key is not None
    assert len(long_key) == len("area:") + 40


@pytest.mark.parametrize(
    "topic,memory_type",
    [
        ("profile", "profile"),
        ("preferences", "preference"),
        ("subjects", "fact"),
        ("goals", "focus"),
        ("progress", "focus"),
        ("struggles", "fact"),
        ("area:science-fair", "project"),
        ("tech-stack", "fact"),
    ],
)
def test_topic_decides_type(topic, memory_type):
    assert topic_memory_type(topic) == memory_type


def test_every_type_default_is_a_standard_topic_of_that_type():
    """Only areas store projects, so a project fact with no area files under Other."""
    keys = {spec.key for spec in STANDARD_TOPICS}
    for memory_type, topic in TYPE_DEFAULT_TOPIC.items():
        assert topic in keys
        expected = "fact" if memory_type == "project" else memory_type
        assert topic_memory_type(topic) == expected


def test_standard_topics_are_what_a_tutor_needs():
    assert [spec.key for spec in STANDARD_TOPICS] == [
        "profile",
        "preferences",
        "subjects",
        "goals",
        "progress",
        "struggles",
        "interests",
        "schedule",
        "notes",
    ]


def test_a_focus_fact_with_no_topic_is_learning_progress():
    assert fact_topic(SimpleNamespace(topic=None, type="focus")) == "progress"


def test_fact_topic_uses_the_stored_topic_or_the_type_default():
    assert fact_topic(SimpleNamespace(topic="area:recall", type="project")) == "area:recall"
    assert fact_topic(SimpleNamespace(topic=None, type="preference")) == "preferences"
