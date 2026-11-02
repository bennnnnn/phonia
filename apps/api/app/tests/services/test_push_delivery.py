"""Push cycle delivery, receipts, and token rebinding."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import TodoItem, User
from app.modules.notifications import push as push_service
from app.modules.todos import due_reminders
from app.tests.fakes import fake_session, redis_mock
from app.tests.services import push_cycle_support as push_cycle
from app.tests.services.push_cycle_support import run_push_cycle


@pytest.fixture
def schedule_write():
    with patch.object(
        due_reminders, "update_schedule_if_current", AsyncMock(return_value=True)
    ) as write:
        yield write


@pytest.mark.asyncio
async def test_run_push_cycle_skips_expo_in_dev_mock():
    session = fake_session()
    redis = redis_mock()
    settings = Settings(
        mock_llm_enabled=True,
        environment="development",
        push_enabled=True,
        server_todo_push_enabled=True,
    )

    with (
        patch.object(
            push_cycle,
            "process_todo_reminders",
            AsyncMock(
                return_value=[
                    push_service.OutboundPush(message={"to": "token"}),
                ]
            ),
        ),
        patch.object(
            push_service.expo_push_gateway, "send_push_messages", AsyncMock()
        ) as send_mock,
    ):
        count = await run_push_cycle(session, redis, settings)

    assert count == 1
    send_mock.assert_not_awaited()


def _users_execute_result(users):
    return MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: users)))


@pytest.mark.asyncio
async def test_run_push_cycle_disabled():
    session = fake_session()
    redis = redis_mock()
    settings = Settings(push_enabled=False)

    count = await run_push_cycle(session, redis, settings)
    assert count == 0


@pytest.mark.asyncio
async def test_run_push_cycle_sends_expo_in_production():
    session = fake_session()
    redis = redis_mock()
    settings = Settings(
        push_enabled=True,
        mock_llm_enabled=False,
        environment="production",
        server_todo_push_enabled=True,
    )

    with (
        patch.object(
            push_cycle,
            "process_todo_reminders",
            AsyncMock(
                return_value=[
                    push_service.OutboundPush(message={"to": "token"}),
                ]
            ),
        ),
        patch.object(
            push_service.expo_push_gateway,
            "send_push_messages",
            AsyncMock(
                return_value=push_service.expo_push_gateway.PushSendResult(
                    invalid_tokens=[],
                    delivered=[True],
                )
            ),
        ) as send_mock,
    ):
        count = await run_push_cycle(session, redis, settings)

    assert count == 1
    send_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_push_cycle_marks_todo_sent_only_after_expo_ok(schedule_write):
    session = fake_session()
    redis = redis_mock()
    settings = Settings(
        push_enabled=True,
        mock_llm_enabled=False,
        environment="production",
        server_todo_push_enabled=True,
    )
    todo = MagicMock()
    todo.notification_sent_at = None

    outbound = [
        push_service.OutboundPush(
            message={"to": "ExponentPushToken[abc]"},
            todos=[todo],
        )
    ]

    with (
        patch.object(
            push_cycle,
            "process_todo_reminders",
            AsyncMock(return_value=outbound),
        ),
        patch.object(
            push_service.expo_push_gateway,
            "send_push_messages",
            AsyncMock(
                return_value=push_service.expo_push_gateway.PushSendResult(
                    invalid_tokens=[],
                    delivered=[True],
                )
            ),
        ),
    ):
        await run_push_cycle(session, redis, settings)

    schedule_write.assert_awaited_once()
    assert schedule_write.await_args.kwargs["notification_sent_at"] is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_conditionally_marks_delivered_snapshot(schedule_write):
    """Persist the collected snapshot through the conditional repository write."""
    finalize_session = AsyncMock()
    now = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
    todo_id = uuid4()
    detached = MagicMock()
    detached.id = todo_id
    detached.notification_sent_at = None

    await push_service.finalize_push_deliveries(
        finalize_session,
        [
            push_service.OutboundPush(
                message={"to": "ExponentPushToken[abc]"},
                todos=[detached],
            )
        ],
        [True],
        now=now,
    )

    schedule_write.assert_awaited_once()
    assert schedule_write.await_args.args[1].id == todo_id
    # A delivery leaves updated_at, which the reminder instant reads, as it was.
    assert schedule_write.await_args.kwargs == {
        "notification_sent_at": now,
        "updated_at": TodoItem.updated_at,
    }
    assert detached.notification_sent_at is None
    finalize_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_skips_when_delivered_snapshot_no_longer_matches(schedule_write):
    finalize_session = AsyncMock()
    now = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
    todo_id = uuid4()
    detached = MagicMock()
    detached.id = todo_id
    detached.notification_sent_at = None
    schedule_write.return_value = False

    await push_service.finalize_push_deliveries(
        finalize_session,
        [
            push_service.OutboundPush(
                message={"to": "ExponentPushToken[abc]"},
                todos=[detached],
            )
        ],
        [True],
        now=now,
    )

    schedule_write.assert_awaited_once()
    assert detached.notification_sent_at is None
    finalize_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_advances_recurring_todo_and_clears_sent(schedule_write):
    finalize_session = AsyncMock()
    now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    due = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)
    todo_id = uuid4()
    user_id = uuid4()
    user = MagicMock()
    user.timezone = "UTC"
    finalize_session.get = AsyncMock(return_value=user)
    detached = MagicMock()
    detached.id = todo_id
    detached.user_id = user_id
    detached.due_at = due
    detached.recurrence_rule = "daily"
    detached.notification_sent_at = now

    await push_service.finalize_push_deliveries(
        finalize_session,
        [
            push_service.OutboundPush(
                message={"to": "ExponentPushToken[abc]"},
                todos=[detached],
            )
        ],
        [True],
        now=now,
    )

    finalize_session.get.assert_awaited_once_with(User, user_id)
    schedule_write.assert_awaited_once()
    fields = schedule_write.await_args.kwargs
    assert fields["due_at"] > due
    assert fields["notification_sent_at"] is None
    assert fields["email_sent_at"] is None
    assert detached.due_at == due
    finalize_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_push_cycle_does_not_mark_todo_when_expo_fails():
    session = fake_session()
    redis = redis_mock()
    settings = Settings(
        push_enabled=True,
        mock_llm_enabled=False,
        environment="production",
        server_todo_push_enabled=True,
    )
    todo = MagicMock()
    todo.notification_sent_at = None

    outbound = [
        push_service.OutboundPush(
            message={"to": "ExponentPushToken[abc]"},
            todos=[todo],
        )
    ]

    with (
        patch.object(
            push_cycle,
            "process_todo_reminders",
            AsyncMock(return_value=outbound),
        ),
        patch.object(
            push_service.expo_push_gateway,
            "send_push_messages",
            AsyncMock(
                return_value=push_service.expo_push_gateway.PushSendResult(
                    invalid_tokens=[],
                    delivered=[False],
                )
            ),
        ),
    ):
        await run_push_cycle(session, redis, settings)

    assert todo.notification_sent_at is None
    session.commit.assert_not_awaited()


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_enqueue_push_receipts_stores_ticket_and_token(fake_redis):
    before = time.time()
    await push_service.enqueue_push_receipts(fake_redis, [("ticket-1", "ExponentPushToken[abc]")])
    assert await fake_redis.zscore(push_service.RECEIPT_PENDING_ZSET, "ticket-1") >= before
    assert await fake_redis.get("recall:push:receipt:token:ticket-1") == "ExponentPushToken[abc]"


@pytest.mark.asyncio
async def test_pending_receipts_are_bounded(fake_redis):
    """The set had no bound: an Expo receipts outage grew it without limit."""
    tickets = [(f"ticket-{i}", f"ExponentPushToken[{i}]") for i in range(15)]
    with patch.object(push_service, "RECEIPT_PENDING_MAX", 10):
        await push_service.enqueue_push_receipts(fake_redis, tickets)
    assert await fake_redis.zcard(push_service.RECEIPT_PENDING_ZSET) == 10


async def _ready_ticket(redis, ticket_id: str, token: str, *, at: float) -> None:
    await redis.zadd(push_service.RECEIPT_PENDING_ZSET, {ticket_id: at})
    await redis.set(f"recall:push:receipt:token:{ticket_id}", token)


@pytest.mark.asyncio
async def test_poll_deferred_push_receipts_prunes_invalid_token(fake_redis):
    session = fake_session()
    await _ready_ticket(fake_redis, "ticket-1", "ExponentPushToken[dead]", at=1_000.0)
    receipts = {"ticket-1": {"status": "error", "details": {"error": "DeviceNotRegistered"}}}
    with (
        patch(
            "app.modules.notifications.push.expo_push_gateway.fetch_push_receipts",
            AsyncMock(return_value=receipts),
        ),
        patch.object(push_service.push_repo, "delete_by_token", AsyncMock()) as delete_mock,
    ):
        await push_service.poll_deferred_push_receipts(session, fake_redis, now=10_000.0)

    delete_mock.assert_awaited_once_with(session, "ExponentPushToken[dead]")
    session.commit.assert_awaited_once()
    assert await fake_redis.zcard(push_service.RECEIPT_PENDING_ZSET) == 0
    assert await fake_redis.get("recall:push:receipt:token:ticket-1") is None


@pytest.mark.asyncio
async def test_poll_deferred_push_receipts_keeps_pending_receipts(fake_redis):
    session = fake_session()
    await _ready_ticket(fake_redis, "ticket-1", "ExponentPushToken[ok]", at=1_000.0)
    with (
        patch(
            "app.modules.notifications.push.expo_push_gateway.fetch_push_receipts",
            AsyncMock(return_value={"ticket-1": {"status": "pending"}}),
        ),
        patch.object(push_service.push_repo, "delete_by_token", AsyncMock()) as delete_mock,
    ):
        await push_service.poll_deferred_push_receipts(session, fake_redis, now=10_000.0)

    delete_mock.assert_not_awaited()
    session.commit.assert_not_awaited()
    assert await fake_redis.zcard(push_service.RECEIPT_PENDING_ZSET) == 1


@pytest.mark.asyncio
async def test_receipt_polling_reads_a_bounded_batch(fake_redis):
    """Polling every ready ticket at once let one Expo outage delay every reminder."""
    for i in range(12):
        await _ready_ticket(fake_redis, f"ticket-{i}", f"ExponentPushToken[{i}]", at=1_000.0)
    fetch = AsyncMock(return_value={})
    with (
        patch("app.modules.notifications.push.expo_push_gateway.fetch_push_receipts", fetch),
        patch.object(push_service, "RECEIPT_POLL_BATCH", 5),
    ):
        await push_service.poll_deferred_push_receipts(AsyncMock(), fake_redis, now=10_000.0)
    assert len(fetch.await_args.args[0]) == 5


@pytest.mark.asyncio
async def test_run_push_cycle_enqueues_receipt_tickets():
    session = fake_session()
    redis = redis_mock()
    settings = Settings(
        push_enabled=True,
        mock_llm_enabled=False,
        environment="production",
        server_todo_push_enabled=True,
    )

    with (
        patch.object(
            push_service,
            "poll_deferred_push_receipts",
            AsyncMock(),
        ),
        patch.object(
            push_cycle,
            "process_todo_reminders",
            AsyncMock(
                return_value=[
                    push_service.OutboundPush(message={"to": "ExponentPushToken[abc]"}),
                ]
            ),
        ),
        patch.object(
            push_service.expo_push_gateway,
            "send_push_messages",
            AsyncMock(
                return_value=push_service.expo_push_gateway.PushSendResult(
                    invalid_tokens=[],
                    delivered=[True],
                    receipt_tickets=[("ticket-1", "ExponentPushToken[abc]")],
                )
            ),
        ),
        patch.object(
            push_service,
            "enqueue_push_receipts",
            AsyncMock(),
        ) as enqueue_mock,
    ):
        await run_push_cycle(session, redis, settings)

    enqueue_mock.assert_awaited_once_with(
        redis,
        [("ticket-1", "ExponentPushToken[abc]")],
    )


@pytest.mark.asyncio
async def test_run_push_cycle_marks_sent_on_ticket_without_receipt_poll(schedule_write):
    """Ticket accept marks delivery; receipt polling is deferred for token pruning only."""
    session = fake_session()
    redis = redis_mock()
    settings = Settings(
        push_enabled=True,
        mock_llm_enabled=False,
        environment="production",
        server_todo_push_enabled=True,
    )
    todo = MagicMock()
    todo.id = uuid4()
    todo.content = "Call dentist"
    todo.notification_sent_at = None

    with (
        patch.object(push_service, "poll_deferred_push_receipts", AsyncMock()),
        patch.object(
            push_cycle,
            "process_todo_reminders",
            AsyncMock(
                return_value=[
                    push_service.OutboundPush(
                        message={"to": "ExponentPushToken[abc]"},
                        todos=[todo],
                    ),
                ]
            ),
        ),
        patch.object(
            push_service.expo_push_gateway,
            "send_push_messages",
            AsyncMock(
                return_value=push_service.expo_push_gateway.PushSendResult(
                    invalid_tokens=[],
                    delivered=[True],
                    receipt_tickets=[("ticket-1", "ExponentPushToken[abc]")],
                )
            ),
        ),
        patch.object(push_service, "enqueue_push_receipts", AsyncMock()) as enqueue_mock,
    ):
        await run_push_cycle(session, redis, settings)

    schedule_write.assert_awaited_once()
    assert schedule_write.await_args.kwargs["notification_sent_at"] is not None
    enqueue_mock.assert_awaited_once()
    session.commit.assert_awaited()


def test_append_outbound_dedupes_duplicate_tokens():
    out: list[push_service.OutboundPush] = []
    token_a = MagicMock()
    token_a.expo_push_token = "ExponentPushToken[abc]"
    token_b = MagicMock()
    token_b.expo_push_token = "ExponentPushToken[abc]"

    push_service._append_outbound(
        out,
        [token_a, token_b],
        title="Reminder",
        body="Call dentist",
        data={"type": "todo_reminder"},
    )

    assert len(out) == 1
    assert out[0].message["to"] == "ExponentPushToken[abc]"


@pytest.mark.asyncio
async def test_upsert_prunes_stale_tokens_for_device():
    from app.repositories import push_tokens as repo

    session = fake_session()
    user_id = uuid4()
    existing = MagicMock()
    existing.user_id = user_id
    existing.device_id = "device-1"
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=existing))

    await repo.upsert(
        session,
        user_id=user_id,
        expo_push_token="ExponentPushToken[new]",
        platform="ios",
        device_id="device-1",
    )

    assert session.execute.await_count == 2
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_rejects_cross_user_rebind_without_device_id():
    from app.exceptions import PushTokenBindError
    from app.repositories import push_tokens as repo

    session = fake_session()
    prior = MagicMock()
    prior.user_id = uuid4()
    prior.device_id = "device-a"
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=prior))

    with pytest.raises(PushTokenBindError, match="device_id is required"):
        await repo.upsert(
            session,
            user_id=uuid4(),
            expo_push_token="ExponentPushToken[stolen]",
            platform="ios",
            device_id=None,
        )


@pytest.mark.asyncio
async def test_upsert_rejects_cross_user_rebind_with_mismatched_device():
    from app.exceptions import PushTokenBindError
    from app.repositories import push_tokens as repo

    session = fake_session()
    prior = MagicMock()
    prior.user_id = uuid4()
    prior.device_id = "device-a"
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=prior))

    with pytest.raises(PushTokenBindError, match="different device"):
        await repo.upsert(
            session,
            user_id=uuid4(),
            expo_push_token="ExponentPushToken[stolen]",
            platform="ios",
            device_id="device-b",
        )


@pytest.mark.asyncio
async def test_upsert_rejects_cross_user_rebind_of_a_row_without_device_id():
    """A row from before device ids has no install to prove: it stays with its owner."""
    from app.exceptions import PushTokenBindError
    from app.repositories import push_tokens as repo

    session = fake_session()
    owner = uuid4()
    prior = MagicMock()
    prior.user_id = owner
    prior.device_id = None
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=prior))

    with pytest.raises(PushTokenBindError):
        await repo.upsert(
            session,
            user_id=uuid4(),
            expo_push_token="ExponentPushToken[legacy]",
            platform="ios",
            device_id="any-device",
        )
    session.delete.assert_not_awaited()
    session.commit.assert_not_awaited()
    assert prior.user_id == owner


@pytest.mark.asyncio
async def test_upsert_allows_cross_user_rebind_with_matching_device():
    from app.repositories import push_tokens as repo

    session = fake_session()
    prior_user = uuid4()
    new_user = uuid4()
    prior = MagicMock()
    prior.user_id = prior_user
    prior.device_id = "device-a"
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=prior))

    row = await repo.upsert(
        session,
        user_id=new_user,
        expo_push_token="ExponentPushToken[shared]",
        platform="ios",
        device_id="device-a",
    )
    assert row.user_id == new_user
    session.delete.assert_awaited_with(prior)
    session.commit.assert_awaited()
