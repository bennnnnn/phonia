from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.modules.memory.documents import area_title_from_key, build_documents

_BASE = datetime(2026, 9, 1, tzinfo=UTC)


def _fact(topic: str, text: str, *, day: int, memory_type: str = "fact", edited_day: int = 0):
    created = _BASE + timedelta(days=day)
    return SimpleNamespace(
        id=uuid4(),
        type=memory_type,
        topic=topic,
        text=text,
        created_at=created,
        updated_at=_BASE + timedelta(days=max(day, edited_day)),
    )


def test_documents_group_facts_by_topic_in_reading_order():
    facts = [
        _fact("tech-stack", "Uses Expo", day=3),
        _fact("area:recall", "Builds Recall", day=2, memory_type="project"),
        _fact("profile", "Name is Sam", day=1, memory_type="profile"),
        _fact("tech-stack", "Uses FastAPI", day=1, edited_day=9),
        _fact("area:zebra", "Runs Zebra", day=4, memory_type="project"),
        _fact("preferences", "Likes short answers", day=5, memory_type="preference"),
    ]
    areas = [SimpleNamespace(key="area:recall", title="Recall", summary="AI chat app")]

    documents = build_documents(facts, areas)

    assert [(doc.group, doc.key) for doc in documents] == [
        ("you", "preferences"),
        ("you", "profile"),
        ("topics", "tech-stack"),
        ("areas", "area:recall"),
        ("areas", "area:zebra"),
    ]
    stack = documents[2]
    assert (stack.title, stack.summary) == ("Tech stack", "Tools and technologies you use")
    # Oldest first; updated is the latest change to any fact.
    assert [fact.text for fact in stack.facts] == ["Uses FastAPI", "Uses Expo"]
    assert stack.updated_at == _BASE + timedelta(days=9)
    recall, zebra = documents[3], documents[4]
    assert (recall.title, recall.summary) == ("Recall", "AI chat app")
    # An area without a title row is named from its key.
    assert (zebra.title, zebra.summary) == ("Zebra", "")


def test_documents_skip_empty_topics():
    assert build_documents([], []) == []


def test_area_title_from_key_reads_the_slug():
    assert area_title_from_key("area:uber-l3-conversion") == "Uber L3 Conversion"
