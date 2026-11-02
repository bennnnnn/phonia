"""RevenueCat event handling: every event that can change access ends with the plan
RevenueCat's subscriber record says, read from its REST API, not from the event body."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest

from app.core.config import Settings
from app.modules.billing import revenuecat

_SUB = "app.modules.billing.revenuecat.subscription_service"


def _settings() -> Settings:
    return Settings(environment="development", revenuecat_secret_key="sk_test")


def _payload(event_type: str, **fields: object) -> dict:
    event = {"type": event_type, "id": str(uuid4()), **fields}
    return {"api_version": "1.0", "event": event}


async def _process(payload: dict) -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await revenuecat.process_event(
        AsyncMock(),
        redis,
        _settings(),
        payload,
        receipt_enqueuer=AsyncMock(),
    )


async def test_an_event_claimed_by_another_delivery_is_busy_before_the_subscriber_lock():
    """The event claim turns away a second delivery of an event in flight, before it
    takes the subscriber lock or asks RevenueCat for the plan."""
    subscriber_lock = AsyncMock(return_value="token")
    resolve = AsyncMock(return_value="pro")
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    payload = _payload("INITIAL_PURCHASE", app_user_id=str(uuid4()))
    with patch(f"{_SUB}.resolve_plan_from_revenuecat", resolve):
        with pytest.raises(revenuecat.SubscriberBusyError):
            await revenuecat.process_event(
                AsyncMock(),
                redis,
                _settings(),
                payload,
                event_claim=AsyncMock(return_value=False),
                subscriber_lock=subscriber_lock,
                receipt_enqueuer=AsyncMock(),
            )
    subscriber_lock.assert_not_awaited()
    resolve.assert_not_awaited()


async def test_transfer_without_app_user_id_moves_the_plan_to_transferred_to():
    """RevenueCat's TRANSFER body has no app_user_id: only transferred_from/_to.

    Two accounts on one Apple ID: B restores, RevenueCat moves the purchase from
    A to B. A must lose the plan and B must get it."""
    old_id, new_id = str(uuid4()), str(uuid4())
    payload = _payload(
        "TRANSFER",
        transferred_from=[old_id],
        transferred_to=[new_id],
        event_timestamp_ms=1_700_000_000_000,
        store="APP_STORE",
        environment="PRODUCTION",
    )
    transfer = AsyncMock(return_value=True)
    with (
        patch(f"{_SUB}.handle_revenuecat_transfer", transfer),
        patch(f"{_SUB}.is_stale_rc_event", AsyncMock(return_value=False)),
        patch(f"{_SUB}.advance_rc_event_watermark", AsyncMock()),
    ):
        await _process(payload)
    transfer.assert_awaited_once()
    assert transfer.await_args.kwargs["new_app_user_id"] == new_id
    assert transfer.await_args.kwargs["transferred_from"] == [old_id]


async def test_transfer_fetch_failure_is_retryable():
    payload = _payload("TRANSFER", transferred_from=[str(uuid4())], transferred_to=[str(uuid4())])
    with (
        patch(f"{_SUB}.handle_revenuecat_transfer", AsyncMock(return_value=False)),
        patch(f"{_SUB}.is_stale_rc_event", AsyncMock(return_value=False)),
        pytest.raises(revenuecat.SubscriberFetchError),
    ):
        await _process(payload)


@pytest.mark.parametrize(
    "payload",
    [
        _payload("EXPIRATION", app_user_id="00000000-0000-0000-0000-000000000001"),
        _payload(
            "CANCELLATION",
            app_user_id="00000000-0000-0000-0000-000000000001",
            expiration_at_ms=1,
        ),
    ],
    ids=["expiration", "cancellation-after-period-end"],
)
async def test_access_ending_event_rechecks_revenuecat_before_downgrading(payload):
    """One product expiring does not end access when another grant still holds
    the entitlement (a promotional grant, a second store, a newer product)."""
    apply_plan = AsyncMock(return_value=False)
    with (
        patch(f"{_SUB}.resolve_plan_from_revenuecat", AsyncMock(return_value="pro")),
        patch(f"{_SUB}.apply_plan_for_app_user_id", apply_plan),
        patch(f"{_SUB}.is_stale_rc_event", AsyncMock(return_value=False)),
        patch(f"{_SUB}.advance_rc_event_watermark", AsyncMock()),
    ):
        await _process(payload)
    apply_plan.assert_awaited_once()
    assert apply_plan.await_args.kwargs["plan"] == "pro"


async def test_expiration_downgrades_when_revenuecat_agrees():
    apply_plan = AsyncMock(return_value=True)
    with (
        patch(f"{_SUB}.resolve_plan_from_revenuecat", AsyncMock(return_value="free")),
        patch(f"{_SUB}.apply_plan_for_app_user_id", apply_plan),
        patch(f"{_SUB}.is_stale_rc_event", AsyncMock(return_value=False)),
        patch(f"{_SUB}.advance_rc_event_watermark", AsyncMock()),
    ):
        await _process(_payload("EXPIRATION", app_user_id=str(uuid4())))
    assert apply_plan.await_args.kwargs["plan"] == "free"


async def test_expiration_fetch_failure_is_retryable():
    with (
        patch(f"{_SUB}.resolve_plan_from_revenuecat", AsyncMock(return_value=None)),
        patch(f"{_SUB}.apply_plan_for_app_user_id", AsyncMock()) as apply_plan,
        patch(f"{_SUB}.is_stale_rc_event", AsyncMock(return_value=False)),
        pytest.raises(revenuecat.SubscriberFetchError),
    ):
        await _process(_payload("EXPIRATION", app_user_id=str(uuid4())))
    apply_plan.assert_not_awaited()


@pytest.mark.parametrize("event_type", ["TEMPORARY_ENTITLEMENT_GRANT", "REFUND_REVERSED"])
async def test_access_granting_events_sync_the_plan(event_type):
    apply_plan = AsyncMock(return_value=True)
    with (
        patch(f"{_SUB}.resolve_plan_from_revenuecat", AsyncMock(return_value="pro")),
        patch(f"{_SUB}.apply_plan_for_app_user_id", apply_plan),
        patch(f"{_SUB}.is_stale_rc_event", AsyncMock(return_value=False)),
        patch(f"{_SUB}.advance_rc_event_watermark", AsyncMock()),
    ):
        await _process(_payload(event_type, app_user_id=str(uuid4())))
    apply_plan.assert_awaited_once()
    assert apply_plan.await_args.kwargs["plan"] == "pro"


@pytest.mark.parametrize(
    "payload",
    [
        _payload("BILLING_ISSUE", app_user_id=str(uuid4()), expiration_at_ms=4_099_689_600_000),
        _payload("SUBSCRIPTION_PAUSED", app_user_id=str(uuid4())),
        _payload(
            "CANCELLATION",
            app_user_id=str(uuid4()),
            cancel_reason="UNSUBSCRIBE",
            expiration_at_ms=4_099_689_600_000,
        ),
    ],
    ids=["billing-issue-grace", "pause-scheduled", "auto-renew-off"],
)
async def test_access_continues_until_expiration(payload):
    resolve = AsyncMock(return_value="free")
    apply_plan = AsyncMock()
    with (
        patch(f"{_SUB}.resolve_plan_from_revenuecat", resolve),
        patch(f"{_SUB}.apply_plan_for_app_user_id", apply_plan),
        patch(f"{_SUB}.is_stale_rc_event", AsyncMock(return_value=False)),
        patch(f"{_SUB}.advance_rc_event_watermark", AsyncMock()),
    ):
        await _process(payload)
    resolve.assert_not_awaited()
    apply_plan.assert_not_awaited()
