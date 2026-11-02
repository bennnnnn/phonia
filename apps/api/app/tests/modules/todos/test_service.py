from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.config import Settings
from app.modules import todos as todos_service
from app.modules.conversation import messages_repository
from app.modules.todos import crud as todos_crud
from app.modules.todos import repository as todos_repo
from app.modules.todos.prompt_context import format_todos_block, should_inject_todos_prompt
from app.modules.todos.prompt_hint import TODO_HINT
from app.modules.todos.schemas import TodoActionItem, TodoCreate, TodoUpdate
from app.tests.fakes import FakeSessionCM, fake_session


def _session_local_side_effect(session: AsyncMock):
    return [FakeSessionCM(session), FakeSessionCM(session)]


@asynccontextmanager
async def _nested_savepoint():
    yield


def _session_with_savepoint() -> AsyncMock:
    """AsyncMock session whose begin_nested() is sync, like SQLAlchemy's."""
    session = fake_session()
    session.begin_nested = MagicMock(side_effect=_nested_savepoint)
    return session


def test_todo_create_accepts_plain_undated_item():
    body = TodoCreate(content="Call mom")
    assert body.due_at is None
    assert body.recurrence_rule is None


def test_todo_schemas_have_no_project_id():
    assert "project_id" not in TodoCreate.model_fields
    assert "project_id" not in TodoUpdate.model_fields
    created = TodoCreate.model_validate({"content": "Call mom", "project_id": str(uuid4())})
    assert "project_id" not in created.model_dump()
    updated = TodoUpdate.model_validate({"project_id": str(uuid4())})
    assert updated.model_dump(exclude_unset=True) == {}


def test_todo_update_accepts_cleared_due_at():
    body = TodoUpdate(due_at=None)
    assert body.model_dump(exclude_unset=True) == {"due_at": None}


@pytest.mark.asyncio
async def test_update_todo_clears_due_at_and_recurrence():
    session = fake_session()
    user = MagicMock()
    user.id = uuid4()
    item = MagicMock()
    item.due_at = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    item.recurrence_rule = "weekly"
    updated = MagicMock()
    with (
        patch.object(todos_crud.todos_repo, "get_by_id", AsyncMock(return_value=item)),
        patch.object(todos_crud.todos_repo, "update", AsyncMock(return_value=updated)) as update,
    ):
        result = await todos_crud.update_todo(session, user, uuid4(), {"due_at": None})
    assert result is updated
    update.assert_awaited_once_with(session, item, due_at=None, recurrence_rule=None)


@pytest.mark.asyncio
async def test_update_todo_rejects_recurrence_without_due():
    session = fake_session()
    user = MagicMock()
    user.id = uuid4()
    user.timezone = "UTC"
    item = MagicMock()
    item.due_at = None
    item.recurrence_rule = None
    with patch.object(todos_crud.todos_repo, "get_by_id", AsyncMock(return_value=item)):
        with pytest.raises(todos_crud.TodosError) as exc:
            await todos_crud.update_todo(session, user, uuid4(), {"recurrence_rule": "weekly"})
    assert exc.value.status_code == 422
    assert "due_at" in exc.value.detail


@pytest.mark.asyncio
async def test_create_todo_unique_violation_returns_existing():
    from sqlalchemy.exc import IntegrityError

    session = fake_session()
    user = MagicMock()
    user.id = uuid4()
    user.timezone = "UTC"
    due = datetime(2026, 9, 8, 15, tzinfo=UTC)
    existing = MagicMock()
    existing.id = uuid4()
    existing.content = "Call mom"
    existing.due_at = due
    with (
        patch.object(
            todos_crud.todos_repo,
            "create",
            AsyncMock(
                side_effect=IntegrityError("insert", {}, Exception("uq_todo_open_content_due"))
            ),
        ),
        patch.object(
            todos_crud.todos_repo,
            "get_open_dated_duplicate",
            AsyncMock(return_value=existing),
        ) as lookup,
    ):
        item = await todos_crud.create_todo(
            session,
            user,
            content="Call mom",
            topic="Reminders",
            chat_id=None,
            due_at=due,
        )
    assert item is existing
    lookup.assert_awaited_once()
    session.rollback.assert_awaited_once()


def test_is_open_content_due_conflict_reads_constraint_name():
    from sqlalchemy.exc import IntegrityError

    hit = IntegrityError("insert", {}, Exception("uq_todo_open_content_due"))
    other = IntegrityError("insert", {}, Exception("todo_items_pkey"))
    assert todos_repo.is_open_content_due_conflict(hit)
    assert not todos_repo.is_open_content_due_conflict(other)


def _item(content: str, topic: str = "Groceries", checked: bool = False):
    item = MagicMock()
    item.id = uuid4()
    item.topic = topic
    item.content = content
    item.checked = checked
    item.due_at = None
    item.source = "user"
    return item


def _item_due_today(content: str, *, hour: int = 9, tz_name: str = "UTC"):
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    due_local = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    item = _item(content)
    item.due_at = due_local.astimezone(UTC)
    return item


def _item_overdue(content: str, *, hours_ago: int = 3, tz_name: str = "UTC"):
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    due_local = datetime.now(tz) - timedelta(hours=hours_ago)
    item = _item(content, topic="Reminders")
    item.due_at = due_local.astimezone(UTC)
    return item


def test_format_todos_block_groups_undated_items_under_anytime():
    block = format_todos_block(
        [
            _item("Milk", "Groceries"),
            _item("Report", "Work"),
            _item("Eggs", "Groceries", checked=True),
        ]
    )
    assert "User To-do list" in block
    assert "### Anytime" in block
    assert "Milk" in block
    assert "Report" in block
    assert "### Completed" in block
    assert "Eggs" in block


def test_format_todos_block_includes_dated_and_plain_items():
    due_item = _item("Reading at 10", "General")
    due_item.due_at = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    block = format_todos_block(
        [
            due_item,
            _item("Milk", "Groceries"),
        ],
        user_timezone="UTC",
    )
    assert "User To-do list" in block
    assert "Reading at 10" in block
    assert "### " in block
    assert "User Lists" not in block
    assert "### Anytime" in block
    assert "Milk" in block


def test_format_todos_voice_block_is_plain_and_includes_undated():
    due_item = _item("Reading at 10", "General")
    due_item.due_at = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    block = todos_service.format_todos_voice_block(
        [due_item, _item("Milk", "Groceries")],
        user_timezone="UTC",
    )
    assert "User To-do list" in block
    assert "Reading at 10" in block
    assert "10:00" in block
    assert "### " not in block
    assert "Anytime: Milk" in block
    assert "Anytime: Milk" in todos_service.format_todos_voice_block([_item("Milk")])


@pytest.mark.asyncio
async def test_apply_todo_actions_complete():
    session = fake_session()
    existing = _item("Buy milk", "Groceries")
    with (
        patch.object(
            todos_repo,
            "list_for_user",
            AsyncMock(return_value=[existing]),
        ),
        patch.object(
            todos_repo,
            "update",
            AsyncMock(return_value=existing),
        ) as update_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[
                TodoActionItem(action="complete", topic="Groceries", content="Buy milk"),
            ],
        )
    assert applied == 1
    update_mock.assert_awaited()


@pytest.mark.asyncio
async def test_apply_todo_actions_set_due():
    session = fake_session()
    existing = _item("Pay rent", "Home")
    due = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    with (
        patch.object(
            todos_repo,
            "list_for_user",
            AsyncMock(return_value=[existing]),
        ),
        patch.object(
            todos_repo,
            "update",
            AsyncMock(return_value=existing),
        ) as update_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[
                TodoActionItem(
                    action="set_due",
                    topic="Home",
                    content="Pay rent",
                    due_at=due,
                )
            ],
            user_timezone="UTC",
        )
    assert applied == 1
    update_mock.assert_awaited()


@pytest.mark.asyncio
async def test_apply_todo_actions_set_due_forwards_recurrence():
    session = fake_session()
    existing = _item("Pay rent", "Home")
    due = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    with (
        patch.object(
            todos_repo,
            "list_for_user",
            AsyncMock(return_value=[existing]),
        ),
        patch.object(
            todos_repo,
            "update",
            AsyncMock(return_value=existing),
        ) as update_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[
                TodoActionItem(
                    action="set_due",
                    topic="Home",
                    content="Pay rent",
                    due_at=due,
                    recurrence_rule="weekly",
                )
            ],
            user_timezone="UTC",
        )
    assert applied == 1
    assert update_mock.await_args.kwargs["recurrence_rule"] == "weekly"


def test_select_todos_for_prompt_prioritizes_overdue():
    now = datetime.now(UTC)
    overdue = _item("Overdue task")
    overdue.due_at = now - timedelta(days=1)
    future = _item("Later task")
    future.due_at = now + timedelta(days=30)
    filler = [_item(f"Filler {i}") for i in range(50)]
    for offset, item in enumerate(filler):
        item.due_at = now + timedelta(days=60 + offset)
    items = [*filler, future, overdue]
    selected = todos_service.select_todos_for_prompt(
        items,
        Settings(todo_prompt_limit=10),
        query_text=None,
        user_timezone="UTC",
    )
    assert overdue in selected
    assert len(selected) == 10
    assert selected.index(overdue) < selected.index(future)


def test_select_todos_for_prompt_keeps_matching_undated_item():
    """A relevant plain task must not be trimmed behind unrelated reminders."""
    now = datetime.now(UTC)
    grocery = _item("Buy groceries for dinner", "General")
    unrelated = [_item(f"Unrelated reminder {i}", "General") for i in range(8)]
    unrelated[0].content = "Show weekly report"
    for offset, item in enumerate(unrelated):
        item.due_at = now + timedelta(hours=offset + 1)

    selected = todos_service.select_todos_for_prompt(
        [*unrelated, grocery],
        Settings(todo_prompt_limit=8),
        query_text="show my grocery list",
        user_timezone="UTC",
    )

    assert grocery in selected
    assert selected[0] is grocery


def test_query_implies_todos():
    assert todos_service.query_implies_todos("What's on my todo list?")
    assert todos_service.query_implies_todos("mis recordatorios")
    assert todos_service.query_implies_todos("remind me to call mom tomorrow at 5pm")
    assert todos_service.query_implies_todos("Can you remind me")
    assert todos_service.query_implies_todos("Add milk to my grocery list")
    assert todos_service.query_implies_todos("mark laundry done")
    assert todos_service.query_implies_todos("move dentist to tomorrow")
    assert todos_service.query_implies_todos("What time is my flight")
    assert todos_service.query_implies_todos("when is the meeting")
    assert not todos_service.query_implies_todos("Who am I?")
    assert not todos_service.query_implies_todos("Explain quantum physics")
    assert not todos_service.query_implies_todos("tell me about flight delays")


@pytest.mark.parametrize(
    ("text", "loads"),
    [
        # The app's own name for the list, however it is spelled (live 2026-10-25).
        ("ok last thing, what's on my to do list right now?", True),
        ("hmm are you sure? check my to-do list again", True),
        ("add milk to my to-do list", True),
        ("put this on my to do list", True),
        ("my to-dos for the move", True),
        ("what do i have today", True),
        ("what do I have tomorrow?", True),
        ("things to do in lisbon", False),
        ("what to do today?", False),
        ("i have a lot to do this week", False),
        ("what do i have to do to get a visa?", False),
        ("how to do long division", False),
    ],
)
def test_query_implies_todos_reads_the_list_by_its_name(text: str, loads: bool) -> None:
    assert todos_service.query_implies_todos(text) is loads


def test_find_item_requires_exact_normalized_match():
    """Destructive todo actions must not fuzzy-match near-miss titles."""
    from app.modules.todos.actions import _find_item

    target = _item("buy organic milk", topic="Groceries")
    near = _item("buy organic milke", topic="Groceries")
    assert _find_item([target, near], "Groceries", "buy organic milk") is target
    assert _find_item([near], "Groceries", "buy organic milk") is None


def test_todo_hint_does_not_promise_unapplied_changes():
    """Fence apply happens before persist; the prompt must not tell the model
    to confirm or to say 'I'll delete' as if that were the saved result."""
    hint = todos_service.TODO_HINT
    assert "before your reply" not in hint
    assert "pre-reply sync" not in hint
    assert "I'll delete" not in hint
    assert "I'll set" not in hint
    assert TODO_HINT in hint
    assert "ask when" in hint
    assert "whole-list delete" not in hint


@pytest.mark.asyncio
async def test_apply_todo_actions_reminder_without_topic():
    """Dated reminder adds work even when the extractor omits a list title."""
    session = _session_with_savepoint()
    due = datetime(2026, 7, 19, 19, 0, tzinfo=UTC)
    with (
        patch.object(
            todos_repo,
            "list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            todos_repo,
            "create",
            AsyncMock(),
        ) as create_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[
                TodoActionItem(
                    action="add",
                    topic="",
                    content="2026 FIFA World Cup Final – Watch the match",
                    due_at=due,
                ),
            ],
            user_timezone="America/New_York",
        )
    assert applied == 1
    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["topic"] == todos_service.REMINDER_TOPIC
    assert kwargs["due_at"] is not None


@pytest.mark.asyncio
async def test_materialize_reminder_fences_creates_todo():
    session = fake_session()
    due = datetime(2026, 7, 19, 19, 0, tzinfo=UTC)
    text = (
        "✅ Reminder set!\n\n"
        "```reminder\n"
        '{"title":"2026 FIFA World Cup Final","due_at":"2026-07-19T15:00:00-04:00"}\n'
        "```\n"
    )
    with (
        patch.object(
            todos_repo,
            "list_for_user",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            todos_repo,
            "create",
            AsyncMock(),
        ) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
        )
    assert created == 1
    assert "```reminder" not in updated
    assert "Reminder set" in updated
    assert "Set: 2026 FIFA World Cup Final —" in updated
    assert "3:00 PM" in updated
    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["topic"] == todos_service.REMINDER_TOPIC
    assert kwargs["content"] == "2026 FIFA World Cup Final"
    assert kwargs["due_at"] is not None
    assert kwargs["due_at"].tzinfo is not None
    # 3pm ET → 19:00 UTC
    assert kwargs["due_at"].hour == due.hour


@pytest.mark.asyncio
async def test_materialize_reminder_fences_respects_user_no_create_request():
    session = fake_session()
    text = (
        "You could use a phone alarm.\n\n"
        "```reminder\n"
        '{"title":"Submit application","due_at":"2026-09-27T15:00:00-07:00"}\n'
        "```\n"
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock()) as list_mock,
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/Los_Angeles",
            user_text=(
                "Don't create a reminder—just tell me how I could remember to submit "
                "my application tomorrow at 3 PM."
            ),
        )

    assert created == 0
    assert updated == "You could use a phone alarm."
    assert "```reminder" not in updated
    list_mock.assert_not_awaited()
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_decline_drops_a_false_set_and_keeps_a_refusal():
    session = fake_session()
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        lied, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Got it! I set a reminder for tomorrow.",
            user_timezone="America/New_York",
            user_text="Don't set a reminder",
        )
        refused, _created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Got it! No reminder set.",
            user_timezone="America/New_York",
            user_text="Don't set a reminder",
        )
    assert created == 0
    assert lied == "I didn't set a reminder."
    assert refused == "Got it! No reminder set."
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_reminder_fence_dates_matching_plain_todo():
    """A dated add promotes the existing plain task instead of only claiming it did."""
    session = fake_session()
    existing = _item("Water plants")
    existing.due_at = None
    existing.recurrence_rule = None
    text = '```reminder\n{"title":"Water plants","due_at":"2026-09-07T18:00:00Z"}\n```\n'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch.object(todos_repo, "update", AsyncMock(return_value=existing)) as update_mock,
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )

    assert created == 1
    assert "Set: Water plants" in updated
    update_mock.assert_awaited_once()
    assert update_mock.await_args.kwargs["due_at"] == datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_reminder_fence_keeps_same_title_on_another_day():
    """Same-title reminders at different instants are not false duplicates."""
    session = fake_session()
    existing = _item("Water plants")
    existing.due_at = datetime(2026, 9, 6, 18, 0, tzinfo=UTC)
    existing.recurrence_rule = None
    text = '```reminder\n{"title":"Water plants","due_at":"2026-09-07T18:00:00Z"}\n```\n'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch.object(todos_repo, "update", AsyncMock()) as update_mock,
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        _updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )

    assert created == 1
    update_mock.assert_not_awaited()
    create_mock.assert_awaited_once()
    assert create_mock.await_args.kwargs["due_at"] == datetime(2026, 9, 7, 18, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_materialize_reminder_fences_unique_race_returns_existing():
    from sqlalchemy.exc import IntegrityError

    session = fake_session()
    due = datetime(2026, 7, 19, 19, 0, tzinfo=UTC)
    existing = MagicMock()
    existing.content = "2026 FIFA World Cup Final"
    existing.due_at = due
    existing.recurrence_rule = None
    existing.checked = False
    text = (
        "```reminder\n"
        '{"title":"2026 FIFA World Cup Final","due_at":"2026-07-19T15:00:00-04:00"}\n'
        "```\n"
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(
            todos_repo,
            "create",
            AsyncMock(
                side_effect=IntegrityError("insert", {}, Exception("uq_todo_open_content_due"))
            ),
        ),
        patch.object(
            todos_repo,
            "get_open_dated_duplicate",
            AsyncMock(return_value=existing),
        ),
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
        )
    assert created == 1
    assert "Set: 2026 FIFA World Cup Final" in updated
    # Only the insert's savepoint is undone; the caller's turn is never rolled back.
    session.rollback.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_reminder_fences_stores_repeat():
    session = fake_session()
    text = (
        "```reminder\n"
        '{"title":"Practice Spanish","due_at":"2026-08-21T08:00:00-04:00","repeat":"daily"}\n'
        "```\n"
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        _updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
        )
    assert created == 1
    assert create_mock.await_args.kwargs["recurrence_rule"] == "daily"


@pytest.mark.asyncio
async def test_materialize_reminder_fences_creates_plain_todo():
    session = fake_session()
    text = 'Hello\n```reminder\n{"title":"x"}\n```\n'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert created == 1
    assert "```reminder" not in updated
    assert "Set: x." in updated
    assert create_mock.await_args.kwargs["due_at"] is None
    assert create_mock.await_args.kwargs["topic"] == todos_repo.DEFAULT_TOPIC


@pytest.mark.asyncio
async def test_add_milk_does_not_confirm_an_invented_time():
    session = fake_session()
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Added: Milk — Buy milk — Saturday, Oct 10, 6:00 PM.",
            user_timezone="America/New_York",
            user_text="Add milk.",
        )
    assert created == 0
    create_mock.assert_not_awaited()
    assert "Added:" not in updated
    assert updated == "When should I remind you?"


@pytest.mark.asyncio
async def test_add_fence_with_a_time_the_user_did_not_say_is_not_saved():
    session = fake_session()
    text = '```reminder\n{"title":"Buy milk","due_at":"2026-10-10T18:00:00-04:00"}\n```'
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
            user_text="Add milk.",
        )
    assert created == 0
    create_mock.assert_not_awaited()
    assert "```reminder" not in updated
    assert updated == "When should I remind you?"


@pytest.mark.asyncio
async def test_add_fence_keeps_a_clock_the_user_stated():
    session = fake_session()
    # Tomorrow, as the user said: a fixed date passes and the fence rejects a past due time.
    new_york = ZoneInfo("America/New_York")
    nine = datetime.combine(datetime.now(new_york).date() + timedelta(days=1), time(9), new_york)
    text = f'```reminder\n{{"title":"Call the bakery","due_at":"{nine.isoformat()}"}}\n```'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
            user_text="Remind me to call the bakery tomorrow at 9:00 in the morning.",
        )
    assert created == 1
    assert "Set: Call the bakery" in updated
    assert create_mock.await_args.kwargs["content"] == "Call the bakery"


@pytest.mark.asyncio
async def test_materialize_reminder_fences_matches_uppercase_tag():
    """The linear scanner keeps the old regex's IGNORECASE language tag."""
    session = fake_session()
    text = 'Sure!\n```REMINDER\n{"title":"Water plants","due_at":"2026-09-07T18:00:00"}\n```\n'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert created == 1
    assert "```REMINDER" not in updated
    create_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_materialize_reminder_fences_ignores_unclosed_fence():
    """No closing triple backtick → no match, text untouched (regex parity)."""
    session = fake_session()
    text = 'Here you go:\n```reminder\n{"title":"Water plants","due_at":"2026-09-07T18:00:00"}\n'
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert created == 0
    assert updated == text
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_reminder_fences_requires_newline_after_tag():
    """A one-line ```reminder {...}``` fence never matched the regex either."""
    session = fake_session()
    text = '```reminder {"title":"Water plants","due_at":"2026-09-07T18:00:00"}```'
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert created == 0
    assert updated == text
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_reminder_fences_rejects_date_only_due():
    session = fake_session()
    text = '```reminder\n{"title":"Water plants","due_at":"2026-09-07"}\n```\n'
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert created == 0
    # Nothing saved and no error text: the reply asks when.
    assert updated == "When should I remind you?"
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_reminder_fences_asks_when_for_a_repeat_with_no_start():
    # "always remind me to drink water" showed "the format was invalid".
    session = fake_session()
    text = '```reminder\n{"title":"Drink water","recurrence_rule":"daily"}\n```\n'
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
            user_text="always remind me to drink water",
        )
    assert created == 0
    assert updated == "When should I remind you?"
    assert "invalid" not in updated
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_reminder_fences_accepts_content_naive_iso_and_extra_keys():
    session = fake_session()
    text = (
        "```reminder\n"
        '{"content":"Water plants","due_at":"2026-09-07T18:00:00",'
        '"notes":"ignore me","priority":1}\n'
        "```\n"
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        _updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
        )
    assert created == 1
    assert create_mock.await_args.kwargs["content"] == "Water plants"
    due = create_mock.await_args.kwargs["due_at"]
    assert due.tzinfo is not None
    # naive 18:00 Eastern (EDT, UTC-4) → 22:00 UTC
    assert due.hour == 22


@pytest.mark.asyncio
async def test_materialize_reminder_fences_accepts_z_suffix_and_wrapped_json():
    session = fake_session()
    text = '```reminder\nHere you go:\n{"title":"Call mom","due_at":"2026-09-07T18:00:00Z"}\n```\n'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        _updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert created == 1
    due = create_mock.await_args.kwargs["due_at"]
    assert due.hour == 18


@pytest.mark.asyncio
async def test_materialize_reminder_from_explicit_user_text_when_fence_missing():
    session = fake_session()
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="I'll set that reminder for tomorrow at 6 PM.",
            user_timezone="UTC",
            user_text="remind me to water the plants tomorrow at 6pm",
        )
    assert created == 1
    assert "```reminder" not in updated
    assert "Set: water the plants" in updated
    assert create_mock.await_args.kwargs["content"] == "water the plants"
    due = create_mock.await_args.kwargs["due_at"]
    assert due.hour == 18
    assert due.tzinfo is not None


@pytest.mark.asyncio
async def test_invalid_reminder_fence_falls_back_to_explicit_user_text():
    """A broken ```reminder must not block 'remind me … tomorrow at 6pm'."""
    session = fake_session()
    text = 'Hello\n```reminder\n{"title":"x","repeat":"daily"}\n```\n'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
            user_text="remind me to water the fern tomorrow at 6pm",
        )
    assert created == 1
    assert "Could not save that to-do" not in updated
    assert "Set: water the fern" in updated
    assert create_mock.await_args.kwargs["content"] == "water the fern"


@pytest.mark.asyncio
async def test_user_remind_without_clock_does_not_invent_a_due():
    session = fake_session()
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Sure, I can remind you.",
            user_timezone="UTC",
            user_text="remind me to water the plants tomorrow",
        )
    assert created == 0
    assert updated == "When should I remind you?"
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_without_a_clock_keeps_a_real_time_question():
    session = fake_session()
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="What time tomorrow?",
            user_timezone="America/New_York",
            user_text="Add read for tomorrow",
        )
    assert created == 0
    assert updated == "What time tomorrow?"
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_without_a_clock_does_not_keep_an_invented_set_line():
    session = fake_session()
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Set: Walk — Sunday, Oct 11, 7:00 PM · weekly.",
            user_timezone="America/New_York",
            user_text="Add a todo walking for tomorrow wekkly",
        )
    assert created == 0
    assert updated == "When should I remind you?"
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_clock_reply_saves_tomorrow_not_a_past_today():
    from zoneinfo import ZoneInfo

    session = fake_session()
    previous = MagicMock()
    previous.role = "user"
    previous.content = "Add read for tommorrow"
    current = MagicMock()
    current.role = "user"
    current.content = "6"
    when = datetime(2026, 10, 10, 22, 8, tzinfo=ZoneInfo("America/New_York"))
    text = "Set: Read — Saturday, Oct 10, 6:00 PM."
    with (
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[previous, current]),
        ),
        patch("app.modules.todos.spoken_add._now", return_value=when),
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
            user_text="6",
        )
    assert created == 1
    assert updated == "Set: read — Sunday, Oct 11, 6:00 PM."
    assert "Saturday" not in updated
    assert create_mock.await_args.kwargs["due_at"] == datetime(2026, 10, 11, 22, 0, tzinfo=UTC)
    assert create_mock.await_args.kwargs["content"] == "read"
    assert create_mock.await_args.kwargs["recurrence_rule"] is None


async def _clock_reply(user_text: str, assistant_text: str) -> tuple[str, int, AsyncMock]:
    """The user answers "when?" for "Add read for tommorrow" late on Saturday in New York."""
    previous = MagicMock()
    previous.role = "user"
    previous.content = "Add read for tommorrow"
    current = MagicMock()
    current.role = "user"
    current.content = user_text
    when = datetime(2026, 10, 10, 22, 8, tzinfo=ZoneInfo("America/New_York"))
    with (
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[previous, current]),
        ),
        patch("app.modules.todos.spoken_add._now", return_value=when),
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            fake_session(),
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=assistant_text,
            user_timezone="America/New_York",
            user_text=user_text,
        )
    return updated, created, create_mock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_text", "due", "line"),
    [
        ("6:30", datetime(2026, 10, 11, 22, 30, tzinfo=UTC), "6:30 PM"),
        ("at 7:15.", datetime(2026, 10, 11, 23, 15, tzinfo=UTC), "7:15 PM"),
        ("12", datetime(2026, 10, 11, 16, 0, tzinfo=UTC), "12:00 PM"),
        ("18", datetime(2026, 10, 11, 22, 0, tzinfo=UTC), "6:00 PM"),
        ("7am", datetime(2026, 10, 11, 11, 0, tzinfo=UTC), "7:00 AM"),
    ],
)
async def test_clock_reply_reads_the_hour_and_minutes(user_text, due, line):
    updated, created, create_mock = await _clock_reply(user_text, "Set: Read — tomorrow.")
    assert created == 1
    assert updated == f"Set: read — Sunday, Oct 11, {line}."
    assert create_mock.await_args.kwargs["due_at"] == due


@pytest.mark.asyncio
@pytest.mark.parametrize("user_text", ["0", "0:30", "00", "24", "1 8", "6pm tomorrow maybe"])
async def test_a_reply_that_is_no_clock_saves_nothing(user_text):
    """ "0" is not noon. Midnight is said as midnight or 12am."""
    updated, created, create_mock = await _clock_reply(
        user_text, "Set: Read — Sunday, Oct 11, 12:00 PM."
    )
    assert created == 0
    create_mock.assert_not_awaited()
    assert "12:00 PM" not in updated


@pytest.mark.asyncio
async def test_clock_reply_keeps_the_repeat_from_the_earlier_add():
    from zoneinfo import ZoneInfo

    session = fake_session()
    previous = MagicMock()
    previous.role = "user"
    previous.content = "Add a todo walking for tomorrow wekkly"
    current = MagicMock()
    current.role = "user"
    current.content = "7pm"
    when = datetime(2026, 10, 10, 22, 8, tzinfo=ZoneInfo("America/New_York"))
    with (
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[previous, current]),
        ),
        patch("app.modules.todos.spoken_add._now", return_value=when),
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Set: Walk — Saturday, Oct 10, 7:00 PM · weekly.",
            user_timezone="America/New_York",
            user_text="7pm",
        )
    assert created == 1
    assert updated == "Set: walking — Sunday, Oct 11, 7:00 PM · weekly."
    assert create_mock.await_args.kwargs["recurrence_rule"] == "weekly"


@pytest.mark.asyncio
async def test_past_fence_is_not_saved_when_the_user_only_said_a_clock():
    session = fake_session()
    text = (
        "Set: Read — Saturday, Oct 10, 6:00 PM.\n"
        '```reminder\n{"title":"Read","due_at":"2026-10-10T18:00:00-04:00"}\n```'
    )
    with (
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
            user_text="6",
        )
    assert created == 0
    assert "Set:" not in updated
    assert "Saturday" not in updated
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_reminder_fences_caps_creates_per_reply():
    session = fake_session()
    over = todos_service.MAX_TODO_ACTIONS_PER_TURN + 3
    fences = [
        f'```reminder\n{{"title":"Task {i}","due_at":"2026-07-19T15:00:00-04:00"}}\n```'
        for i in range(over)
    ]
    text = "\n".join(fences)

    async def _create(_session, **kwargs):
        item = MagicMock()
        item.content = kwargs["content"]
        item.due_at = kwargs["due_at"]
        item.checked = False
        return item

    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock(side_effect=_create)) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert created == todos_service.MAX_TODO_ACTIONS_PER_TURN
    assert create_mock.await_count == todos_service.MAX_TODO_ACTIONS_PER_TURN
    assert "```reminder" not in updated


@pytest.mark.asyncio
async def test_materialize_reminder_fences_deletes_and_confirms():
    session = fake_session()
    existing = _item("Walk", topic=todos_service.REMINDER_TOPIC)
    text = '```reminder\n{"action":"delete","title":"Walk"}\n```'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch.object(todos_repo, "delete_by_id", AsyncMock(return_value=True)) as delete_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert applied == 1
    assert "```reminder" not in updated
    assert updated.strip() == "Deleted: Walk."
    delete_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_materialize_reminder_fences_delete_miss_says_so():
    session = fake_session()
    text = '```reminder\n{"action":"delete","title":"Walk"}\n```'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "delete_by_id", AsyncMock()) as delete_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert applied == 0
    assert "Could not delete Walk." in updated
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_spoken_mark_done_checks_and_ignores_a_delete_fence():
    session = fake_session()
    existing = _item("Call the bakery", topic=todos_service.REMINDER_TOPIC)
    text = 'Deleted!\n\n```reminder\n{"action":"delete","title":"Call the bakery"}\n```'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch.object(todos_repo, "update", AsyncMock(return_value=existing)) as update_mock,
        patch.object(todos_repo, "delete_by_id", AsyncMock()) as delete_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
            user_text="Mark the bakery call done.",
        )
    assert applied == 1
    assert updated == "Done: Call the bakery."
    assert update_mock.await_args.kwargs["checked"] is True
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_spoken_reopen_unchecks_and_does_not_create():
    session = fake_session()
    existing = _item("Stretch", topic=todos_service.REMINDER_TOPIC, checked=True)
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch.object(todos_repo, "update", AsyncMock(return_value=existing)) as update_mock,
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Open: Stretch.",
            user_timezone="America/New_York",
            user_text="Reopen the stretch reminder.",
        )
    assert applied == 1
    assert updated == "Reopened: Stretch."
    assert update_mock.await_args.kwargs["checked"] is False
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_spoken_reopen_of_a_missing_reminder_does_not_create():
    session = fake_session()
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="I'll add Stretch again.",
            user_timezone="America/New_York",
            user_text="Reopen the stretch reminder.",
        )
    assert applied == 0
    assert updated == "Could not reopen stretch."
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_spoken_move_sets_the_clock_and_repeat():
    from zoneinfo import ZoneInfo

    session = fake_session()
    existing = _item("Call the dentist", topic=todos_service.REMINDER_TOPIC)
    existing.due_at = datetime(2026, 10, 11, 20, 0, tzinfo=UTC)
    when = datetime(2026, 10, 10, 18, 0, tzinfo=ZoneInfo("America/New_York"))
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch.object(todos_repo, "update", AsyncMock(return_value=existing)) as update_mock,
        patch("app.modules.todos.spoken_change._now", return_value=when),
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Updated: Stretch — Monday at 8.",
            user_timezone="America/New_York",
            user_text="Move the dentist call to Monday at 8:00 PM and make it weekly.",
        )
    assert applied == 1
    assert updated == "Moved: Call the dentist — Monday, Oct 12, 8:00 PM · weekly."
    assert update_mock.await_args.kwargs["due_at"] == datetime(2026, 10, 13, 0, 0, tzinfo=UTC)
    assert update_mock.await_args.kwargs["recurrence_rule"] == "weekly"


@pytest.mark.asyncio
async def test_spoken_delete_removes_the_named_reminder():
    session = fake_session()
    existing = _item("Call the dentist", topic=todos_service.REMINDER_TOPIC)
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch.object(todos_repo, "delete_by_id", AsyncMock(return_value=True)) as delete_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Got it—reminder deleted.",
            user_timezone="America/New_York",
            user_text="Delete the dentist reminder.",
        )
    assert applied == 1
    assert updated == "Deleted: Call the dentist."
    delete_mock.assert_awaited_once()


def _read_item(
    content: str,
    *,
    due: datetime,
    updated: datetime,
    checked: bool = False,
    repeat: str | None = None,
    topic: str = "Reminders",
):
    item = _item(content, topic=topic, checked=checked)
    item.due_at = due
    item.updated_at = updated
    item.created_at = updated
    item.recurrence_rule = repeat
    return item


@pytest.mark.asyncio
async def test_make_it_everyday_sets_daily_and_keeps_the_clock():
    session = fake_session()
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 2, 0, tzinfo=UTC),
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[read])),
        patch.object(todos_repo, "update", AsyncMock(return_value=read)) as update_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Got it! Set: read — 6:00 PM · daily.",
            user_timezone="America/New_York",
            user_text="Make it for everyday",
        )
    assert applied == 1
    assert updated == "Moved: read — Sunday, Oct 11, 6:00 PM · daily."
    assert "Got it" not in updated
    assert update_mock.await_args.kwargs["recurrence_rule"] == "daily"
    assert "due_at" not in update_mock.await_args.kwargs


@pytest.mark.asyncio
async def test_make_it_weekly_replaces_the_repeat_only():
    session = fake_session()
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 2, 0, tzinfo=UTC),
        repeat="daily",
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[read])),
        patch.object(todos_repo, "update", AsyncMock(return_value=read)) as update_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Changed to weekly! You’ll now get a reminder every Sunday at 8:00 AM.",
            user_timezone="America/New_York",
            user_text="Make it weekly",
        )
    assert applied == 1
    assert updated == "Moved: read — Sunday, Oct 11, 6:00 PM · weekly."
    assert "8:00 AM" not in updated
    assert update_mock.await_args.kwargs["recurrence_rule"] == "weekly"
    assert "due_at" not in update_mock.await_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phrase", "hour", "minute", "label"),
    [
        ("Make it 8:00 AM", 8, 0, "8:00 AM"),
        ("Make it 8:00 PM", 20, 0, "8:00 PM"),
        # No am/pm: the evening, as "make it 7" is 7 PM and a reply "6:30" is 6:30 PM.
        ("Make it 6:30", 18, 30, "6:30 PM"),
        ("Make it 7", 19, 0, "7:00 PM"),
        ("Make it 18:45", 18, 45, "6:45 PM"),
    ],
)
async def test_make_it_changes_am_and_pm_on_the_same_day(
    phrase: str, hour: int, minute: int, label: str
):
    from zoneinfo import ZoneInfo

    session = fake_session()
    ny = ZoneInfo("America/New_York")
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 2, 0, tzinfo=UTC),
        repeat="daily",
    )
    when = datetime(2026, 10, 10, 22, 0, tzinfo=ny)
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[read])),
        patch.object(todos_repo, "update", AsyncMock(return_value=read)) as update_mock,
        patch("app.modules.todos.spoken_change._now", return_value=when),
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Updated! Your reminder is now 8:00.",
            user_timezone="America/New_York",
            user_text=phrase,
        )
    assert applied == 1
    assert updated == f"Moved: read — Sunday, Oct 11, {label} · daily."
    assert update_mock.await_args is not None
    saved = update_mock.await_args.kwargs
    assert saved["due_at"] == datetime(2026, 10, 11, hour, minute, tzinfo=ny)
    assert "recurrence_rule" not in saved


@pytest.mark.asyncio
async def test_put_it_in_health_changes_the_topic():
    session = fake_session()
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 2, 0, tzinfo=UTC),
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[read])),
        patch.object(todos_repo, "update", AsyncMock(return_value=read)) as update_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Done! Added your weekly read reminder to Health.",
            user_timezone="America/New_York",
            user_text="Put it in Health",
        )
    assert applied == 1
    assert updated == "Moved: read to Health — Sunday, Oct 11, 6:00 PM."
    assert update_mock.await_args.kwargs["topic"] == "Health"
    assert "due_at" not in update_mock.await_args.kwargs


@pytest.mark.asyncio
async def test_mark_it_done_checks_the_latest_reminder_only():
    session = fake_session()
    bakery = _read_item(
        "call the bakery",
        due=datetime(2026, 10, 11, 13, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 1, 0, tzinfo=UTC),
    )
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 2, 0, tzinfo=UTC),
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[bakery, read])),
        patch.object(todos_repo, "update", AsyncMock(return_value=read)) as update_mock,
        patch.object(todos_repo, "delete_by_id", AsyncMock()) as delete_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Marked as done! Let me know if you need anything else.",
            user_timezone="America/New_York",
            user_text="Mark it done",
        )
    assert applied == 1
    assert updated == "Done: read."
    assert update_mock.await_args.args[1] is read
    assert update_mock.await_args.kwargs["checked"] is True
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_reopen_it_unchecks_the_latest_done_reminder():
    session = fake_session()
    bakery = _read_item(
        "call the bakery",
        due=datetime(2026, 10, 11, 13, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 1, 0, tzinfo=UTC),
    )
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 3, 0, tzinfo=UTC),
        checked=True,
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[bakery, read])),
        patch.object(todos_repo, "update", AsyncMock(return_value=read)) as update_mock,
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Opened it again.",
            user_timezone="America/New_York",
            user_text="Reopen it",
        )
    assert applied == 1
    assert updated == "Reopened: read."
    assert update_mock.await_args.args[1] is read
    assert update_mock.await_args.kwargs["checked"] is False
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_it_removes_the_latest_reminder():
    session = fake_session()
    bakery = _read_item(
        "call the bakery",
        due=datetime(2026, 10, 11, 13, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 1, 0, tzinfo=UTC),
    )
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 3, 0, tzinfo=UTC),
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[bakery, read])),
        patch.object(todos_repo, "delete_by_id", AsyncMock(return_value=True)) as delete_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Deleted!",
            user_timezone="America/New_York",
            user_text="Delete it",
        )
    assert applied == 1
    assert updated == "Deleted: read."
    assert delete_mock.await_args.args[1] == read.id


@pytest.mark.asyncio
async def test_move_it_uses_the_latest_reminder():
    from zoneinfo import ZoneInfo

    session = fake_session()
    ny = ZoneInfo("America/New_York")
    bakery = _read_item(
        "call the bakery",
        due=datetime(2026, 10, 11, 13, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 1, 0, tzinfo=UTC),
    )
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 3, 0, tzinfo=UTC),
    )
    when = datetime(2026, 10, 10, 22, 0, tzinfo=ny)
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[bakery, read])),
        patch.object(todos_repo, "update", AsyncMock(return_value=read)) as update_mock,
        patch("app.modules.todos.spoken_change._now", return_value=when),
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Moved the bakery.",
            user_timezone="America/New_York",
            user_text="Move it to Monday at 4:00 PM",
        )
    assert applied == 1
    assert updated == "Moved: read — Monday, Oct 12, 4:00 PM."
    assert update_mock.await_args.args[1] is read
    assert update_mock.await_args.kwargs["due_at"] == datetime(2026, 10, 12, 20, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_reading_reminders_uses_saved_rows_only():
    session = fake_session()
    bakery = _read_item(
        "call the bakery",
        due=datetime(2026, 10, 11, 13, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 1, 0, tzinfo=UTC),
    )
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 2, 0, tzinfo=UTC),
        repeat="daily",
        topic="Health",
    )
    stretch = _read_item(
        "stretch",
        due=datetime(2026, 10, 12, 10, 30, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 4, 0, tzinfo=UTC),
        checked=True,
    )
    with patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[bakery, read, stretch])):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="You also have a dentist appointment tomorrow.",
            user_timezone="America/New_York",
            user_text="what reminders do I have",
        )
    assert applied == 0
    assert updated == (
        "call the bakery — Sunday, Oct 11, 9:00 AM.\n"
        "read — Sunday, Oct 11, 6:00 PM · daily · Health.\n"
        "Done: stretch."
    )
    assert "dentist" not in updated


@pytest.mark.asyncio
async def test_make_it_with_nothing_saved_does_not_claim_success():
    session = fake_session()
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "update", AsyncMock()) as update_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Got it! Set: read — 6:00 PM · daily.",
            user_timezone="America/New_York",
            user_text="Make it for everyday",
        )
    assert applied == 0
    assert updated == "Could not reschedule that reminder."
    assert "Set:" not in updated
    update_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_added_claim_without_a_clock_asks_instead_of_confirming():
    session = fake_session()
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=(
                "For tomorrow, I’ve added your reminder to **read**. Is there a specific time?"
            ),
            user_timezone="America/New_York",
            user_text="Add read for tomorrow",
        )
    assert created == 0
    assert updated == "When should I remind you?"
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_milk_does_not_claim_a_grocery_list():
    session = fake_session()
    with patch.object(todos_repo, "create", AsyncMock()) as create_mock:
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="I'll add milk to your grocery list.",
            user_timezone="America/New_York",
            user_text="Add milk",
        )
    assert created == 0
    assert updated == "When should I remind you?"
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_weekdays_reminder_saves_the_morning_clock():
    from zoneinfo import ZoneInfo

    session = fake_session()
    ny = ZoneInfo("America/New_York")
    when = datetime(2026, 10, 10, 22, 0, tzinfo=ny)
    with (
        patch("app.modules.todos.spoken_add._now", return_value=when),
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock()) as create_mock,
    ):
        updated, created = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Set: Stretch — Sunday, Oct 11, 6:30 AM · weekdays.",
            user_timezone="America/New_York",
            user_text="Remind me to stretch tomorrow at 6:30 AM on weekdays",
        )
    assert created == 1
    assert updated == "Set: stretch — Monday, Oct 12, 6:30 AM · weekdays."
    assert create_mock.await_args.kwargs["recurrence_rule"] == "weekdays"
    assert create_mock.await_args.kwargs["due_at"] == datetime(2026, 10, 12, 10, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_change_to_a_day_without_a_clock_asks():
    session = fake_session()
    read = _read_item(
        "read",
        due=datetime(2026, 10, 11, 22, 0, tzinfo=UTC),
        updated=datetime(2026, 10, 11, 2, 0, tzinfo=UTC),
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[read])),
        patch.object(todos_repo, "update", AsyncMock()) as update_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text="Moved: read — Monday, Oct 12, 8:00 AM.",
            user_timezone="America/New_York",
            user_text="Change it to Monday",
        )
    assert applied == 0
    assert updated == "When should I remind you?"
    update_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_reminder_fences_set_due_confirms():
    session = fake_session()
    existing = _item("Walk", topic=todos_service.REMINDER_TOPIC)
    existing.due_at = datetime(2026, 7, 19, 19, 0, tzinfo=UTC)
    text = (
        '```reminder\n{"action":"set_due","title":"Walk","due_at":"2026-07-20T15:00:00-04:00"}\n```'
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch.object(todos_repo, "update", AsyncMock(return_value=existing)),
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
        )
    assert applied == 1
    assert "Moved: Walk — Monday, Jul 20, 3:00 PM." in updated


@pytest.mark.asyncio
async def test_materialize_reminder_fences_set_due_forwards_repeat():
    session = fake_session()
    existing = _item("Walk", topic=todos_service.REMINDER_TOPIC)
    existing.due_at = datetime(2026, 7, 19, 19, 0, tzinfo=UTC)
    text = (
        '```reminder\n{"action":"set_due","title":"Walk",'
        '"due_at":"2026-07-20T15:00:00-04:00","repeat":"weekly"}\n```'
    )
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch.object(todos_repo, "update", AsyncMock(return_value=existing)) as update_mock,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="America/New_York",
        )
    assert applied == 1
    assert update_mock.await_args.kwargs["recurrence_rule"] == "weekly"
    assert "Moved: Walk — Monday, Jul 20, 3:00 PM · weekly." in updated


@pytest.mark.asyncio
async def test_materialize_reminder_fences_clears_date_using_existing_topic():
    session = fake_session()
    existing = _item("Walk", topic="Personal")
    existing.due_at = datetime.now(UTC) + timedelta(days=1)
    text = '```reminder\n{"action":"clear_due","title":"Walk"}\n```'
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[existing])),
        patch(
            "app.modules.todos.reminder_writes.apply_todo_actions",
            AsyncMock(return_value=1),
        ) as apply,
    ):
        updated, applied = await todos_service.materialize_reminder_fences(
            session,
            user_id=uuid4(),
            chat_id=uuid4(),
            assistant_text=text,
            user_timezone="UTC",
        )
    assert applied == 1
    assert updated == "Date removed: Walk."
    action = apply.await_args.kwargs["actions"][0]
    assert action.action == "clear_due"
    assert action.topic == "Personal"


def test_format_schedule_result_set_line():
    from app.modules.todos.reminder_writes import format_schedule_result

    due = datetime(2026, 7, 19, 19, 0, tzinfo=UTC)
    line = format_schedule_result(
        action="add",
        title="Call Mom",
        due_at=due,
        repeat="weekly",
        user_timezone="America/New_York",
        ok=True,
    )
    assert line == "Set: Call Mom — Sunday, Jul 19, 3:00 PM · weekly."


def test_todo_hint_covers_reminder_confirm_timing():
    hint = todos_service.TODO_HINT
    assert "```reminder" in hint
    assert TODO_HINT in hint
    assert TODO_HINT in hint
    assert TODO_HINT in hint
    assert TODO_HINT in hint
    assert "do not ask" in hint and "flight number" in hint
    assert TODO_HINT in hint


def test_should_inject_todos_prompt():
    overdue = _item("Late task")
    overdue.due_at = datetime.now(UTC) - timedelta(days=1)
    assert should_inject_todos_prompt([overdue], query_text="Tell me a joke", user_timezone="UTC")
    assert not should_inject_todos_prompt(
        [_item("Milk")], query_text="Tell me a joke", user_timezone="UTC"
    )
    assert should_inject_todos_prompt(
        [_item("Milk")], query_text="Show my grocery list", user_timezone="UTC"
    )
    assert should_inject_todos_prompt(
        [_item("Milk")],
        query_text="How's my day looking so far — anything you think I should prioritize?",
        user_timezone="UTC",
    )


@pytest.mark.asyncio
async def test_apply_todo_actions_creates_undated_add():
    session = _session_with_savepoint()
    created = _item("Buy milk", "Groceries")
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock(return_value=created)) as create_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[
                TodoActionItem(action="add", topic="Groceries", content="Buy milk"),
            ],
        )
    assert applied == 1
    assert create_mock.await_args.kwargs["due_at"] is None
    assert create_mock.await_args.kwargs["topic"] == "Groceries"


@pytest.mark.asyncio
async def test_apply_todo_actions_defaults_plain_add_to_general():
    session = _session_with_savepoint()
    created = _item("Buy milk", todos_repo.DEFAULT_TOPIC)
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(todos_repo, "create", AsyncMock(return_value=created)) as create_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[TodoActionItem(action="add", content="Buy milk")],
        )
    assert applied == 1
    assert create_mock.await_args.kwargs["topic"] == todos_repo.DEFAULT_TOPIC


@pytest.mark.asyncio
async def test_apply_todo_actions_dedupes_add():
    session = fake_session()
    existing = _item("Buy milk", "Groceries")
    existing.due_at = datetime.now(UTC) + timedelta(days=1)
    with (
        patch.object(
            todos_repo,
            "list_for_user",
            AsyncMock(return_value=[existing]),
        ),
        patch.object(
            todos_repo,
            "create",
            AsyncMock(),
        ) as create_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[
                TodoActionItem(
                    action="add",
                    topic="Groceries",
                    content="Buy milk",
                    due_at=existing.due_at,
                ),
            ],
        )
    assert applied == 0
    create_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_todo_actions_add_appends_for_same_batch_dedupe():
    """After an add, the next action must see the new row in state.items
    without a full list_for_user reload."""
    session = _session_with_savepoint()
    due = datetime.now(UTC) + timedelta(days=1)
    created = _item("Eggs", "Groceries")
    created.due_at = due
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])) as list_mock,
        patch.object(todos_repo, "create", AsyncMock(return_value=created)) as create_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[
                TodoActionItem(action="add", topic="Groceries", content="Eggs", due_at=due),
                TodoActionItem(action="add", topic="Groceries", content="Eggs", due_at=due),
            ],
        )
    assert applied == 1
    create_mock.assert_awaited_once()
    assert create_mock.await_args.kwargs.get("commit") is False
    assert list_mock.await_count == 1
    # The caller commits (code-health audit ARCH-07); each action and the first insert
    # have their own savepoint, the duplicate add writes nothing.
    session.commit.assert_not_awaited()
    assert session.begin_nested.call_count == 3


@pytest.mark.asyncio
async def test_apply_todo_actions_unique_violation_counts_zero():
    from sqlalchemy.exc import IntegrityError

    session = _session_with_savepoint()
    due = datetime.now(UTC) + timedelta(days=1)
    with (
        patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[])),
        patch.object(
            todos_repo,
            "create",
            AsyncMock(
                side_effect=IntegrityError("insert", {}, Exception("uq_todo_open_content_due"))
            ),
        ) as create_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[
                TodoActionItem(
                    action="add",
                    topic="Reminders",
                    content="Call mom",
                    due_at=due,
                ),
            ],
        )
    assert applied == 0
    create_mock.assert_awaited_once()
    session.rollback.assert_not_awaited()
    # The action's savepoint and the insert's.
    assert session.begin_nested.call_count == 2


@pytest.mark.asyncio
async def test_apply_todo_actions_wildcard_set_due_today():
    session = fake_session()
    due_today_a = _item_due_today("Walk", hour=9)
    due_today_b = _item_due_today("Call", hour=14)
    list_item = _item("Milk")
    new_due = datetime.now(UTC) + timedelta(days=1)
    with (
        patch.object(
            todos_repo,
            "list_for_user",
            AsyncMock(return_value=[due_today_a, due_today_b, list_item]),
        ),
        patch.object(
            todos_repo,
            "update",
            AsyncMock(side_effect=lambda _s, item, **fields: item),
        ) as update_mock,
    ):
        applied = await todos_service.apply_todo_actions(
            session,
            user_id=uuid4(),
            actions=[
                TodoActionItem(
                    action="set_due",
                    topic="General",
                    content="*",
                    due_at=new_due,
                )
            ],
            user_timezone="UTC",
        )
    assert applied == 2
    assert update_mock.await_count == 2


@pytest.mark.asyncio
async def test_list_todos_advances_past_due_daily():
    session = fake_session()
    past = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
    now = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
    item = MagicMock()
    item.checked = False
    item.due_at = past
    item.recurrence_rule = "daily"
    item.notification_sent_at = now
    item.email_sent_at = now

    with patch.object(todos_crud, "advance_schedules_if_current", AsyncMock()) as advance:
        assert await todos_crud.advance_past_recurring(session, [item], timezone="UTC", now=now)

    advance.assert_awaited_once()
    snapshot, new_due = advance.await_args.args[1][0]
    assert snapshot.due_at == past
    assert new_due > now
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_todo_clears_sent_markers_when_due_changes():
    session = fake_session()
    user = MagicMock()
    user.id = uuid4()
    user.timezone = "UTC"
    item = MagicMock()
    item.due_at = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    item.recurrence_rule = None
    new_due = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)

    with (
        patch.object(todos_crud.todos_repo, "get_by_id", AsyncMock(return_value=item)),
    ):
        await todos_crud.update_todo(session, user, uuid4(), {"due_at": new_due})

    assert item.notification_sent_at is None
    assert item.email_sent_at is None


@pytest.mark.asyncio
async def test_build_todos_system_section_skips_unrelated_query():
    session = fake_session()
    user = MagicMock()
    user.id = uuid4()
    user.timezone = "UTC"
    list_mock = AsyncMock(return_value=[_item("Task")])
    with (
        patch.object(todos_repo, "list_due_soon", AsyncMock(return_value=[])),
        patch.object(todos_repo, "list_for_user", list_mock),
    ):
        section = await todos_service.build_todos_system_section(
            session, user, Settings(), query_text="Who am I?"
        )
    assert section is None
    list_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_todos_system_section_returns_hint_and_block():
    session = fake_session()
    user = MagicMock()
    user.id = uuid4()
    user.timezone = "UTC"
    dated = _item("Task")
    dated.due_at = datetime.now(UTC) + timedelta(hours=2)
    with (
        patch.object(
            todos_repo,
            "list_for_user",
            AsyncMock(return_value=[dated]),
        ),
    ):
        section = await todos_service.build_todos_system_section(
            session, user, Settings(), query_text="Show my tasks"
        )
    assert section is not None
    assert "To-do" in section
    assert "dates are optional" in section
    assert "two todo features" not in section
    assert TODO_HINT in section
    assert "Task" in section


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "locale", "read_only"),
    [
        ("añade comprar leche a mis tareas", "en", True),
        ("напомни завтра позвонить маме", "en", True),
        # A question is still answered from the list; the line says so.
        ("¿qué tengo hoy?", "en", True),
        # English writes, whatever the app language.
        ("add milk to my tasks", "es", False),
        ("show my tasks", "en", False),
    ],
)
async def test_a_turn_in_another_language_is_told_it_only_reads_to_dos(
    query: str, locale: str, read_only: bool
) -> None:
    from app.modules.todos.prompt_hint import TODO_READ_ONLY_HINT

    user = MagicMock(id=uuid4(), timezone="UTC", locale=locale)
    with patch.object(todos_repo, "list_for_user", AsyncMock(return_value=[_item("Task")])):
        section = await todos_service.build_todos_system_section(
            fake_session(), user, Settings(), query_text=query
        )
    assert section is not None
    # A read-only turn is never taught the write fence; an English one is.
    assert section.startswith(TODO_READ_ONLY_HINT if read_only else TODO_HINT)
    assert ("```reminder" in section) is not read_only
