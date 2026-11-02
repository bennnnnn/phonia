from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.schemas import ProductEventBatchIn
from app.modules.analytics import service as product_analytics
from app.tests.fakes import fake_session


@pytest.mark.asyncio
async def test_record_batch_persists_allowlisted_metadata() -> None:
    session = AsyncMock()
    batch = ProductEventBatchIn.model_validate(
        {
            "events": [
                {
                    "name": "paywall_viewed",
                    "properties": {"source": "settings"},
                    "platform": "ios",
                    "app_version": "1.2.3",
                    "installation_id": "install-id",
                }
            ]
        }
    )

    with patch(
        "app.modules.analytics.service.product_events_repo.create_batch",
        AsyncMock(),
    ) as create_batch:
        await product_analytics.record_batch(session, uuid4(), batch)

    call = create_batch.await_args
    assert call is not None
    rows = call.args[1]
    assert len(rows) == 1
    assert rows[0].name == "paywall_viewed"
    assert rows[0].properties == {"source": "settings"}
    create_batch.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_batch_accepts_bucketed_chat_ttft_only() -> None:
    session = AsyncMock()
    batch = ProductEventBatchIn.model_validate(
        {
            "events": [
                {
                    "name": "chat_ttft",
                    "properties": {
                        "latency_bucket": "2000_3999",
                        "transport": "sse",
                        "has_attachment": "no",
                        "sample_rate": "0.2",
                    },
                }
            ]
        }
    )

    with patch(
        "app.modules.analytics.service.product_events_repo.create_batch",
        AsyncMock(),
    ) as create_batch:
        await product_analytics.record_batch(session, uuid4(), batch)

    call = create_batch.await_args
    assert call is not None
    rows = call.args[1]
    assert rows[0].name == "chat_ttft"
    assert rows[0].properties == {
        "latency_bucket": "2000_3999",
        "transport": "sse",
        "has_attachment": "no",
        "sample_rate": "0.2",
    }


@pytest.mark.asyncio
async def test_record_batch_rejects_raw_chat_latency_value() -> None:
    session = AsyncMock()
    batch = ProductEventBatchIn.model_validate(
        {
            "events": [
                {
                    "name": "chat_ttft",
                    "properties": {
                        "latency_bucket": "4821",
                        "transport": "ws",
                        "has_attachment": "no",
                        "sample_rate": "0.2",
                    },
                }
            ]
        }
    )

    with patch(
        "app.modules.analytics.service.product_events_repo.create_batch",
        AsyncMock(),
    ) as create_batch:
        with pytest.raises(ValueError, match="Invalid latency_bucket"):
            await product_analytics.record_batch(session, uuid4(), batch)

    create_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_batch_rejects_unexpected_properties() -> None:
    session = AsyncMock()
    batch = ProductEventBatchIn.model_validate(
        {
            "events": [
                {
                    "name": "purchase_started",
                    "properties": {"prompt": "never store this"},
                }
            ]
        }
    )

    with patch(
        "app.modules.analytics.service.product_events_repo.create_batch",
        AsyncMock(),
    ) as create_batch:
        with pytest.raises(ValueError, match="Invalid properties"):
            await product_analytics.record_batch(session, uuid4(), batch)

    create_batch.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_batch_rolls_back_failed_persistence() -> None:
    session = AsyncMock()
    batch = ProductEventBatchIn.model_validate(
        {"events": [{"name": "purchase_succeeded", "properties": {"plan": "plus"}}]}
    )

    with patch(
        "app.modules.analytics.service.product_events_repo.create_batch",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    ):
        with pytest.raises(RuntimeError, match="database unavailable"):
            await product_analytics.record_batch(session, uuid4(), batch)

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


_OUTCOME = {
    "completion": "stopped",
    "error_code": "none",
    "tool": "searching",
    "sample_rate": "0.2",
}


@pytest.mark.asyncio
async def test_record_batch_accepts_a_metadata_only_chat_turn_outcome() -> None:
    session = AsyncMock()
    batch = ProductEventBatchIn.model_validate(
        {"events": [{"name": "chat_turn_outcome", "properties": _OUTCOME, "platform": "ios"}]}
    )
    with patch(
        "app.modules.analytics.service.product_events_repo.create_batch", AsyncMock()
    ) as create_batch:
        await product_analytics.record_batch(session, uuid4(), batch)

    call = create_batch.await_args
    assert call is not None
    assert call.args[1][0].properties == _OUTCOME


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "properties",
    [
        {**_OUTCOME, "error_code": "That model isn't responding right now."},
        {**_OUTCOME, "tool": "searching for flights to Lagos"},
        {**_OUTCOME, "completion": "user typed: what is my salary"},
        {**_OUTCOME, "prompt": "never store this"},
        {"completion": "complete", "error_code": "none"},
    ],
)
async def test_record_batch_rejects_free_text_in_a_chat_turn_outcome(
    properties: dict[str, str],
) -> None:
    session = AsyncMock()
    batch = ProductEventBatchIn.model_validate(
        {"events": [{"name": "chat_turn_outcome", "properties": properties}]}
    )
    with patch(
        "app.modules.analytics.service.product_events_repo.create_batch", AsyncMock()
    ) as create_batch:
        with pytest.raises(ValueError, match="Invalid"):
            await product_analytics.record_batch(session, uuid4(), batch)
    create_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_database_stores_chat_ttft_and_chat_turn_outcome(db_session) -> None:
    """Regression: chat_ttft was allowlisted but the table's check constraint
    refused it, so every sample failed at commit (migration 0113)."""
    from app.repositories import users

    user = await users.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Analytics",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    batch = ProductEventBatchIn.model_validate(
        {
            "events": [
                {"name": "chat_turn_outcome", "properties": _OUTCOME},
                {
                    "name": "chat_ttft",
                    "properties": {
                        "latency_bucket": "lt500",
                        "transport": "ws",
                        "has_attachment": "no",
                        "sample_rate": "0.2",
                    },
                },
            ]
        }
    )
    await product_analytics.record_batch(db_session, user.id, batch)


_TTFT = {
    "latency_bucket": "500_999",
    "transport": "ws",
    "has_attachment": "no",
    "sample_rate": "0.2",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "properties"),
    [
        ("chat_ttft", _TTFT),
        ("chat_ttft", {**_TTFT, "paint_bucket": "lt50"}),
        ("chat_turn_outcome", _OUTCOME),
        ("chat_turn_outcome", {**_OUTCOME, "send_ready_bucket": "100_249"}),
        ("chat_turn_outcome", {**_OUTCOME, "send_ready_bucket": "none"}),
    ],
)
async def test_record_batch_takes_the_newer_bucketed_fields_or_none(
    name: str, properties: dict[str, str]
) -> None:
    """Apps that predate a field still send the event without it."""
    session = fake_session()
    batch = ProductEventBatchIn.model_validate(
        {"events": [{"name": name, "properties": properties}]}
    )
    with patch(
        "app.modules.analytics.service.product_events_repo.create_batch", AsyncMock()
    ) as create_batch:
        await product_analytics.record_batch(session, uuid4(), batch)

    call = create_batch.await_args
    assert call is not None
    assert call.args[1][0].properties == properties


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "properties"),
    [
        ("chat_ttft", {**_TTFT, "paint_bucket": "37"}),
        ("chat_turn_outcome", {**_OUTCOME, "send_ready_bucket": "412"}),
        # A field belongs to its own event only.
        ("chat_ttft", {**_TTFT, "send_ready_bucket": "lt100"}),
        ("chat_turn_outcome", {**_OUTCOME, "paint_bucket": "lt50"}),
        # The newer field never stands in for a required one.
        ("chat_ttft", {"transport": "ws", "has_attachment": "no", "paint_bucket": "lt50"}),
    ],
)
async def test_record_batch_rejects_raw_or_misplaced_newer_fields(
    name: str, properties: dict[str, str]
) -> None:
    session = fake_session()
    batch = ProductEventBatchIn.model_validate(
        {"events": [{"name": name, "properties": properties}]}
    )
    with patch(
        "app.modules.analytics.service.product_events_repo.create_batch", AsyncMock()
    ) as create_batch:
        with pytest.raises(ValueError, match="Invalid"):
            await product_analytics.record_batch(session, uuid4(), batch)
    create_batch.assert_not_awaited()
