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
        _fact("subjects", "Takes AP Chemistry", day=3),
        _fact("area:science-fair", "Tests plant growth", day=2, memory_type="project"),
        _fact("profile", "Name is Sam", day=1, memory_type="profile"),
        _fact("subjects", "Takes Algebra 2", day=1, edited_day=9),
        _fact("area:zebra", "Runs Zebra", day=4, memory_type="project"),
        _fact("preferences", "Likes short answers", day=5, memory_type="preference"),
    ]
    areas = [SimpleNamespace(key="area:science-fair", title="Science fair", summary="Plants")]

    documents = build_documents(facts, areas)

    assert [(doc.group, doc.key) for doc in documents] == [
        ("you", "preferences"),
        ("you", "profile"),
        ("topics", "subjects"),
        ("areas", "area:science-fair"),
        ("areas", "area:zebra"),
    ]
    subjects = documents[2]
    assert (subjects.title, subjects.summary) == ("Subjects", "What you study and at what level")
    # Oldest first; updated is the latest change to any fact.
    assert [fact.text for fact in subjects.facts] == ["Takes Algebra 2", "Takes AP Chemistry"]
    assert subjects.updated_at == _BASE + timedelta(days=9)
    fair, zebra = documents[3], documents[4]
    assert (fair.title, fair.summary) == ("Science fair", "Plants")
    # An area without a title row is named from its key.
    assert (zebra.title, zebra.summary) == ("Zebra", "")


def test_documents_skip_empty_topics():
    assert build_documents([], []) == []


def test_area_title_from_key_reads_the_slug():
    assert area_title_from_key("area:uber-l3-conversion") == "Uber L3 Conversion"
