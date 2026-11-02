"""PostgreSQL behaviour of memory documents: topics on facts and area rows."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.orm import Memory, MemoryArea
from app.modules.memory import repository as memories_repo
from app.modules.memory.writes_repository import MemoryFactWrite, apply_fact_ops
from app.repositories import users as users_repo


async def _make_user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


def _add(text: str, *, memory_type: str = "fact", topic: str | None = None, **kwargs):
    return MemoryFactWrite(
        op="add", type=memory_type, text=text, confidence=0.9, topic=topic, **kwargs
    )


@pytest.mark.asyncio
async def test_a_fact_saved_without_a_topic_gets_its_types_document(db_session):
    user = await _make_user(db_session)
    row = Memory(user_id=user.id, type="preference", text="Likes short answers")
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)
    assert row.topic == "preferences"


@pytest.mark.asyncio
async def test_writes_store_topics_and_create_area_rows(db_session):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session,
        user.id,
        [
            _add(
                "User is doing a science fair project",
                memory_type="project",
                topic="area:science-fair",
                area_title="Science fair",
                area_summary="Plant growth under light",
            ),
            _add("User takes AP Physics", topic="subjects"),
            _add("User likes chess"),
        ],
        None,
        active_cap=150,
    )
    await db_session.flush()

    facts = await memories_repo.list_for_user(db_session, user.id)
    topics = {fact.text: fact.topic for fact in facts}
    assert topics == {
        "User is doing a science fair project": "area:science-fair",
        "User takes AP Physics": "subjects",
        "User likes chess": "notes",
    }
    areas = await memories_repo.list_areas(db_session, user.id)
    assert [(area.key, area.title, area.summary) for area in areas] == [
        ("area:science-fair", "Science fair", "Plant growth under light")
    ]


@pytest.mark.asyncio
async def test_a_second_title_for_an_area_keeps_the_first(db_session):
    user = await _make_user(db_session)
    for title in ["Science fair", "Science fair (renamed)"]:
        await apply_fact_ops(
            db_session,
            user.id,
            [_add(f"Fact under {title}", topic="area:science-fair", area_title=title)],
            None,
            active_cap=150,
        )
    await db_session.flush()
    areas = await memories_repo.list_areas(db_session, user.id)
    assert [area.title for area in areas] == ["Science fair"]


@pytest.mark.asyncio
async def test_an_update_moves_a_fact_to_another_document_without_a_copy(db_session):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session, user.id, [_add("User is preparing a fair project")], None, active_cap=150
    )
    await db_session.flush()

    await apply_fact_ops(
        db_session,
        user.id,
        [
            MemoryFactWrite(
                op="update",
                type="project",
                text="User is testing plant growth for the science fair",
                confidence=0.9,
                match_text="User is preparing a fair project",
                topic="area:science-fair",
            )
        ],
        None,
        active_cap=150,
    )
    await db_session.flush()

    facts = await memories_repo.list_for_user(db_session, user.id)
    assert [(fact.text, fact.topic, fact.type) for fact in facts] == [
        ("User is testing plant growth for the science fair", "area:science-fair", "project")
    ]


@pytest.mark.asyncio
async def test_an_add_of_the_same_text_under_another_type_is_not_a_copy(db_session):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session,
        user.id,
        [_add("User takes Algebra 2", memory_type="focus")],
        None,
        active_cap=150,
    )
    await apply_fact_ops(
        db_session,
        user.id,
        [_add("User takes Algebra 2", memory_type="fact", topic="subjects")],
        None,
        active_cap=150,
    )
    await db_session.flush()

    facts = await memories_repo.list_for_user(db_session, user.id)
    assert [(fact.text, fact.topic, fact.type) for fact in facts] == [
        ("User takes Algebra 2", "subjects", "fact")
    ]


@pytest.mark.asyncio
async def test_an_update_without_a_topic_keeps_the_facts_document(db_session):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session, user.id, [_add("User takes Biology", topic="subjects")], None, active_cap=150
    )
    await apply_fact_ops(
        db_session,
        user.id,
        [
            MemoryFactWrite(
                op="update",
                type="fact",
                text="User takes AP Biology",
                confidence=0.9,
                match_text="User takes Biology",
            )
        ],
        None,
        active_cap=150,
    )
    await db_session.flush()
    facts = await memories_repo.list_for_user(db_session, user.id)
    assert [(fact.text, fact.topic) for fact in facts] == [("User takes AP Biology", "subjects")]


@pytest.mark.asyncio
async def test_delete_topic_removes_the_document_and_its_area(db_session):
    user = await _make_user(db_session)
    other = await _make_user(db_session)
    for owner in (user, other):
        await apply_fact_ops(
            db_session,
            owner.id,
            [
                _add(
                    "User is doing a science fair project",
                    topic="area:science-fair",
                    area_title="Science fair",
                ),
                _add("User likes chess", topic="interests"),
            ],
            None,
            active_cap=150,
        )
    await db_session.flush()

    deleted = await memories_repo.delete_topic(db_session, user.id, "area:science-fair")

    assert deleted == 1
    assert [fact.topic for fact in await memories_repo.list_for_user(db_session, user.id)] == [
        "interests"
    ]
    assert await memories_repo.list_areas(db_session, user.id) == []
    # Another user's document of the same name is untouched.
    assert len(await memories_repo.list_areas(db_session, other.id)) == 1


@pytest.mark.asyncio
async def test_clearing_all_memory_removes_area_titles(db_session):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session,
        user.id,
        [
            _add(
                "User is doing a science fair project",
                topic="area:science-fair",
                area_title="Science fair",
            )
        ],
        None,
        active_cap=150,
    )
    await db_session.flush()
    areas = select(MemoryArea).where(MemoryArea.user_id == user.id)
    assert (await db_session.execute(areas)).scalars().all() != []

    await memories_repo.delete_all_for_user(db_session, user.id)

    assert (await db_session.execute(areas)).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "new_type,expected",
    [("fact", ("subjects", "fact")), ("profile", ("profile", "profile"))],
)
async def test_a_superseding_fact_keeps_type_and_document_together(db_session, new_type, expected):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session, user.id, [_add("User takes Biology", topic="subjects")], None, active_cap=150
    )
    await apply_fact_ops(
        db_session,
        user.id,
        [
            MemoryFactWrite(
                op="supersede",
                type=new_type,
                text="User switched to AP Biology",
                confidence=0.9,
                match_text="User takes Biology",
            )
        ],
        None,
        active_cap=150,
    )
    await db_session.flush()
    facts = await memories_repo.list_for_user(db_session, user.id)
    assert [(fact.topic, fact.type) for fact in facts] == [expected]
