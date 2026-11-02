from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.gateways import revenuecat_gateway
from app.modules.billing import subscription as subscription_service
from app.tests.fakes import make_user


def test_entitlement_active_lifetime():
    payload = {
        "subscriber": {
            "entitlements": {
                "pro": {"expires_date": None},
            }
        }
    }
    assert revenuecat_gateway.entitlement_active(payload, "pro") is True


def test_entitlement_active_future_expiry():
    future = (datetime.now(UTC) + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    payload = {"subscriber": {"entitlements": {"pro": {"expires_date": future}}}}
    assert revenuecat_gateway.entitlement_active(payload, "pro") is True


def test_entitlement_active_expired():
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    payload = {"subscriber": {"entitlements": {"pro": {"expires_date": past}}}}
    assert revenuecat_gateway.entitlement_active(payload, "pro") is False


def _rc_time(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize(
    "expires, grace, active",
    [
        (timedelta(days=-1), timedelta(days=6), True),  # BILLING_ISSUE: store grace period
        (timedelta(days=-1), timedelta(minutes=-5), False),  # grace over too
        (timedelta(days=-1), None, False),
        (timedelta(days=-1), "", False),
        (timedelta(days=-1), "not-a-date", False),
        (timedelta(days=3), timedelta(days=-10), True),  # an old grace never cuts access
        ("not-a-date", timedelta(days=2), True),
    ],
)
def test_entitlement_active_honors_the_grace_period(expires, grace, active) -> None:
    def _field(value):
        return _rc_time(value) if isinstance(value, timedelta) else value

    ent = {"expires_date": _field(expires), "grace_period_expires_date": _field(grace)}
    payload = {"subscriber": {"entitlements": {"pro": ent}}}
    assert revenuecat_gateway.entitlement_active(payload, "pro") is active


@pytest.mark.asyncio
async def test_reconcile_keeps_a_grace_period_subscriber_paid():
    """The hourly reconcile and app-open sync read the same entitlement rule."""
    ent = {
        "expires_date": _rc_time(timedelta(hours=-2)),
        "grace_period_expires_date": _rc_time(timedelta(days=5)),
    }
    payload = {"subscriber": {"entitlements": {"plus": ent}}}
    with patch.object(
        subscription_service.revenuecat_gateway,
        "fetch_subscriber",
        AsyncMock(return_value=payload),
    ):
        plan = await subscription_service.resolve_plan_from_revenuecat(
            Settings(revenuecat_secret_key="sk_test"), str(uuid4())
        )
    assert plan == "plus"


@pytest.mark.asyncio
async def test_sync_user_plan_from_revenuecat_upgrades():
    user = MagicMock()
    user.id = uuid4()
    user.plan = "free"
    session = AsyncMock()
    settings = Settings(revenuecat_secret_key="sk_test", revenuecat_entitlement_id="pro")
    payload = {"subscriber": {"entitlements": {"pro": {"expires_date": None}}}}

    with patch(
        "app.modules.billing.subscription.revenuecat_gateway.fetch_subscriber",
        AsyncMock(return_value=payload),
    ):
        with patch(
            "app.modules.billing.subscription.users_repo.update",
            AsyncMock(return_value=MagicMock(plan="pro")),
        ) as update:
            updated = await subscription_service.sync_user_plan_from_revenuecat(
                session, user, settings
            )
    assert updated.plan == "pro"
    update.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_user_plan_when_the_store_does_not_answer_is_a_503():
    """No answer is not "still free": the phone then says the plan will update shortly."""
    user = make_user(plan="free")
    settings = Settings(revenuecat_secret_key="sk_test")
    with (
        patch(
            "app.modules.billing.subscription.revenuecat_gateway.fetch_subscriber",
            AsyncMock(return_value=None),
        ),
        pytest.raises(subscription_service.StoreUnreachableError) as caught,
    ):
        await subscription_service.sync_user_plan_from_revenuecat(AsyncMock(), user, settings)
    assert (caught.value.status_code, caught.value.code) == (503, "store_unreachable")


@pytest.mark.asyncio
async def test_apply_plan_for_app_user_id():
    user_id = uuid4()
    user = MagicMock()
    user.plan = "free"
    session = AsyncMock()

    with patch(
        "app.modules.billing.subscription.users_repo.get_by_id",
        AsyncMock(return_value=user),
    ):
        with patch(
            "app.modules.billing.subscription.users_repo.update",
            AsyncMock(return_value=MagicMock(plan="pro")),
        ) as update:
            ok = await subscription_service.apply_plan_for_app_user_id(
                session,
                str(user_id),
                plan="pro",
            )
    assert ok is True
    update.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_plan_replay_publishes_the_unchanged_plan():
    """A redelivery after a change whose publish failed (503) must reach every machine's
    cached copy: the plan is already saved, so the no-change path publishes."""
    user = MagicMock(id=uuid4(), plan="pro")

    with (
        patch(
            "app.modules.billing.subscription.users_repo.get_by_id",
            AsyncMock(return_value=user),
        ),
        patch("app.modules.billing.subscription.users_repo.update", AsyncMock()) as update,
        patch("app.modules.billing.subscription.user_cache.publish_change", AsyncMock()) as publish,
    ):
        applied = await subscription_service.apply_plan_for_app_user_id(
            AsyncMock(), str(user.id), plan="pro"
        )

    assert applied is False
    update.assert_not_awaited()
    publish.assert_awaited_once_with(user.id)


@pytest.mark.asyncio
async def test_is_stale_rc_event_when_older_than_watermark():
    user_id = uuid4()
    user = MagicMock()
    user.rc_last_event_at_ms = 200
    session = AsyncMock()

    with patch(
        "app.modules.billing.subscription.users_repo.get_by_id",
        AsyncMock(return_value=user),
    ):
        assert await subscription_service.is_stale_rc_event(session, str(user_id), 100) is True
        assert await subscription_service.is_stale_rc_event(session, str(user_id), 200) is False
        assert await subscription_service.is_stale_rc_event(session, str(user_id), 250) is False


@pytest.mark.asyncio
async def test_is_stale_rc_event_false_when_no_watermark():
    user_id = uuid4()
    user = MagicMock()
    user.rc_last_event_at_ms = None
    session = AsyncMock()

    with patch(
        "app.modules.billing.subscription.users_repo.get_by_id",
        AsyncMock(return_value=user),
    ):
        assert await subscription_service.is_stale_rc_event(session, str(user_id), 100) is False


@pytest.mark.asyncio
async def test_advance_rc_event_watermark_moves_forward_only():
    user_id = uuid4()
    user = MagicMock()
    user.rc_last_event_at_ms = 200
    session = AsyncMock()

    with patch(
        "app.modules.billing.subscription.users_repo.get_by_id",
        AsyncMock(return_value=user),
    ):
        with patch(
            "app.modules.billing.subscription.users_repo.update",
            AsyncMock(return_value=user),
        ) as update:
            await subscription_service.advance_rc_event_watermark(session, str(user_id), 150)
            update.assert_not_awaited()

            await subscription_service.advance_rc_event_watermark(session, str(user_id), 200)
            update.assert_not_awaited()

            await subscription_service.advance_rc_event_watermark(session, str(user_id), 250)
            update.assert_awaited_once_with(session, user, rc_last_event_at_ms=250)


@pytest.mark.asyncio
async def test_handle_revenuecat_transfer_downgrades_old_and_syncs_new():
    old_id = uuid4()
    new_id = uuid4()
    user = MagicMock()
    user.id = new_id
    user.plan = "free"
    session = AsyncMock()
    settings = Settings(revenuecat_secret_key="sk_test", revenuecat_entitlement_id="pro")

    plans = {str(new_id): "pro", str(old_id): "free"}
    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(side_effect=lambda _settings, app_user_id: plans[app_user_id]),
        ) as resolve_mock,
        patch(
            "app.modules.billing.subscription.users_repo.get_by_id",
            AsyncMock(return_value=user),
        ),
        patch(
            "app.modules.billing.subscription.users_repo.update",
            AsyncMock(return_value=user),
        ) as update,
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
    ):
        ok = await subscription_service.handle_revenuecat_transfer(
            session,
            settings,
            new_app_user_id=str(new_id),
            transferred_from=[str(old_id), "  "],
        )

    assert ok is True
    update.assert_not_awaited()
    assert apply_mock.await_count == 2
    apply_mock.assert_any_await(session, str(new_id), plan="pro")
    apply_mock.assert_any_await(session, str(old_id), plan="free")
    # The target is read before any write; then each source is re-read.
    assert [call.args[1] for call in resolve_mock.await_args_list] == [str(new_id), str(old_id)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_reads, source_plan",
    [
        ("free", "free"),  # its only grant moved
        ("plus", "plus"),  # it still holds another product or a promotional grant
        ("pro", "pro"),
        (None, "free"),  # unreadable: the moved entitlement is no longer its own
    ],
)
async def test_handle_revenuecat_transfer_rereads_each_source(
    source_reads: str | None, source_plan: str
):
    old_id, new_id = str(uuid4()), str(uuid4())
    target = MagicMock()
    target.plan = "pro"
    plans = {new_id: "pro", old_id: source_reads}
    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(side_effect=lambda _settings, app_user_id: plans[app_user_id]),
        ),
        patch(
            "app.modules.billing.subscription.users_repo.get_by_id",
            AsyncMock(return_value=target),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
    ):
        ok = await subscription_service.handle_revenuecat_transfer(
            AsyncMock(),
            Settings(revenuecat_secret_key="sk_test"),
            new_app_user_id=new_id,
            transferred_from=[old_id],
        )

    assert ok is True
    apply_mock.assert_awaited_once()
    source_call = apply_mock.await_args
    assert source_call is not None
    assert source_call.args[1] == old_id
    assert source_call.kwargs["plan"] == source_plan


@pytest.mark.asyncio
async def test_handle_revenuecat_transfer_skips_invalid_new_id():
    session = AsyncMock()
    settings = Settings()

    with (
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(),
        ) as apply_mock,
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(),
        ) as resolve_mock,
    ):
        ok = await subscription_service.handle_revenuecat_transfer(
            session,
            settings,
            new_app_user_id="not-a-uuid",
            transferred_from=["someone"],
        )

    assert ok is False
    apply_mock.assert_not_awaited()
    resolve_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_revenuecat_transfer_does_not_downgrade_when_fetch_fails():
    old_id = uuid4()
    new_id = uuid4()
    session = AsyncMock()
    settings = Settings(revenuecat_secret_key="sk_test")

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(),
        ) as apply_mock,
        patch(
            "app.modules.billing.subscription.users_repo.get_by_id",
            AsyncMock(),
        ) as get_mock,
    ):
        ok = await subscription_service.handle_revenuecat_transfer(
            session,
            settings,
            new_app_user_id=str(new_id),
            transferred_from=[str(old_id)],
        )

    assert ok is False
    apply_mock.assert_not_awaited()
    get_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_plan_from_revenuecat_none_without_secret():
    settings = Settings(revenuecat_secret_key="")
    with patch(
        "app.modules.billing.subscription.revenuecat_gateway.fetch_subscriber",
        AsyncMock(),
    ) as fetch:
        assert await subscription_service.resolve_plan_from_revenuecat(settings, "u") is None
    fetch.assert_not_awaited()
