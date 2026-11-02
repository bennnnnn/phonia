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
        ("tech-stack", "tech-stack"),
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
        ("tech-stack", "fact"),
        ("recent-work", "focus"),
        ("side-projects", "project"),
        ("area:recall", "project"),
    ],
)
def test_topic_decides_type(topic, memory_type):
    assert topic_memory_type(topic) == memory_type


def test_every_type_default_is_a_standard_topic_of_that_type():
    keys = {spec.key for spec in STANDARD_TOPICS}
    for memory_type, topic in TYPE_DEFAULT_TOPIC.items():
        assert topic in keys
        assert topic_memory_type(topic) == memory_type


def test_fact_topic_uses_the_stored_topic_or_the_type_default():
    assert fact_topic(SimpleNamespace(topic="area:recall", type="project")) == "area:recall"
    assert fact_topic(SimpleNamespace(topic=None, type="preference")) == "preferences"
