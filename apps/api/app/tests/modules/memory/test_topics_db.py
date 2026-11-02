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
                "User is building Recall",
                memory_type="project",
                topic="area:recall",
                area_title="Recall",
                area_summary="Personal AI chat app",
            ),
            _add("User uses FastAPI", topic="tech-stack"),
            _add("User likes chess"),
        ],
        None,
        active_cap=150,
    )
    await db_session.flush()

    facts = await memories_repo.list_for_user(db_session, user.id)
    topics = {fact.text: fact.topic for fact in facts}
    assert topics == {
        "User is building Recall": "area:recall",
        "User uses FastAPI": "tech-stack",
        "User likes chess": "notes",
    }
    areas = await memories_repo.list_areas(db_session, user.id)
    assert [(area.key, area.title, area.summary) for area in areas] == [
        ("area:recall", "Recall", "Personal AI chat app")
    ]


@pytest.mark.asyncio
async def test_a_second_title_for_an_area_keeps_the_first(db_session):
    user = await _make_user(db_session)
    for title in ["Recall", "Recall app (renamed)"]:
        await apply_fact_ops(
            db_session,
            user.id,
            [_add(f"Fact under {title}", topic="area:recall", area_title=title)],
            None,
            active_cap=150,
        )
    await db_session.flush()
    areas = await memories_repo.list_areas(db_session, user.id)
    assert [area.title for area in areas] == ["Recall"]


@pytest.mark.asyncio
async def test_an_update_moves_a_fact_to_another_document_without_a_copy(db_session):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session, user.id, [_add("User builds apps with Expo")], None, active_cap=150
    )
    await db_session.flush()

    await apply_fact_ops(
        db_session,
        user.id,
        [
            MemoryFactWrite(
                op="update",
                type="project",
                text="User builds Recall with Expo",
                confidence=0.9,
                match_text="User builds apps with Expo",
                topic="area:recall",
            )
        ],
        None,
        active_cap=150,
    )
    await db_session.flush()

    facts = await memories_repo.list_for_user(db_session, user.id)
    assert [(fact.text, fact.topic, fact.type) for fact in facts] == [
        ("User builds Recall with Expo", "area:recall", "project")
    ]


@pytest.mark.asyncio
async def test_an_add_of_the_same_text_under_another_type_is_not_a_copy(db_session):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session,
        user.id,
        [_add("User codes in TypeScript", memory_type="focus")],
        None,
        active_cap=150,
    )
    await apply_fact_ops(
        db_session,
        user.id,
        [_add("User codes in TypeScript", memory_type="fact", topic="tech-stack")],
        None,
        active_cap=150,
    )
    await db_session.flush()

    facts = await memories_repo.list_for_user(db_session, user.id)
    assert [(fact.text, fact.topic, fact.type) for fact in facts] == [
        ("User codes in TypeScript", "tech-stack", "fact")
    ]


@pytest.mark.asyncio
async def test_an_update_without_a_topic_keeps_the_facts_document(db_session):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session, user.id, [_add("User uses Vim", topic="tech-stack")], None, active_cap=150
    )
    await apply_fact_ops(
        db_session,
        user.id,
        [
            MemoryFactWrite(
                op="update",
                type="fact",
                text="User uses Neovim",
                confidence=0.9,
                match_text="User uses Vim",
            )
        ],
        None,
        active_cap=150,
    )
    await db_session.flush()
    facts = await memories_repo.list_for_user(db_session, user.id)
    assert [(fact.text, fact.topic) for fact in facts] == [("User uses Neovim", "tech-stack")]


@pytest.mark.asyncio
async def test_delete_topic_removes_the_document_and_its_area(db_session):
    user = await _make_user(db_session)
    other = await _make_user(db_session)
    for owner in (user, other):
        await apply_fact_ops(
            db_session,
            owner.id,
            [
                _add("User builds Recall", topic="area:recall", area_title="Recall"),
                _add("User likes chess", topic="interests"),
            ],
            None,
            active_cap=150,
        )
    await db_session.flush()

    deleted = await memories_repo.delete_topic(db_session, user.id, "area:recall")

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
        [_add("User builds Recall", topic="area:recall", area_title="Recall")],
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
    [("fact", ("tech-stack", "fact")), ("profile", ("profile", "profile"))],
)
async def test_a_superseding_fact_keeps_type_and_document_together(db_session, new_type, expected):
    user = await _make_user(db_session)
    await apply_fact_ops(
        db_session, user.id, [_add("User uses Vim", topic="tech-stack")], None, active_cap=150
    )
    await apply_fact_ops(
        db_session,
        user.id,
        [
            MemoryFactWrite(
                op="supersede",
                type=new_type,
                text="User switched to Neovim",
                confidence=0.9,
                match_text="User uses Vim",
            )
        ],
        None,
        active_cap=150,
    )
    await db_session.flush()
    facts = await memories_repo.list_for_user(db_session, user.id)
    assert [(fact.topic, fact.type) for fact in facts] == [expected]
