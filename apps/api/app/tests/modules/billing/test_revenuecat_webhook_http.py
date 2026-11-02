"""The RevenueCat webhook over HTTP: auth, dedupe, ordering, plan changes."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

# ── webhooks / transactional email ────────────────────────────────────────────


def test_revenuecat_webhook_enqueues_receipt_on_purchase():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "app_user_id": str(uid),
            "store": "app_store",
            "product_id": "recall.pro.monthly",
            "expiration_at_ms": 1753977600000,
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()) as enq,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    enq.assert_awaited_once()
    kwargs = enq.await_args.kwargs
    assert kwargs["event_type"] == "INITIAL_PURCHASE"
    assert kwargs["store"] == "app_store"
    assert kwargs["product_id"] == "recall.pro.monthly"
    assert kwargs["expiration"] is not None


def test_revenuecat_webhook_skips_receipt_when_plan_not_applied():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {"event": {"type": "INITIAL_PURCHASE", "app_user_id": str(uid)}}

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=False),
        ),
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()) as enq,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    enq.assert_not_awaited()


def test_revenuecat_webhook_free_event_does_not_enqueue_receipt():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {"event": {"type": "EXPIRATION", "app_user_id": str(uid)}}

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()) as enq,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    enq.assert_not_awaited()


def test_revenuecat_webhook_cancellation_with_future_expiry_keeps_pro():
    """CANCELLATION = auto-renew off; paid-through time must not be stripped."""
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    # Far-future paid-through timestamp (year 2099).
    payload = {
        "event": {
            "type": "CANCELLATION",
            "app_user_id": str(uid),
            "expiration_at_ms": 4099689600000,
        }
    }

    with patch(
        "app.modules.billing.subscription.apply_plan_for_app_user_id",
        AsyncMock(return_value=True),
    ) as apply_plan:
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    apply_plan.assert_not_awaited()


def test_revenuecat_webhook_cancellation_with_past_expiry_downgrades():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "CANCELLATION",
            "app_user_id": str(uid),
            "expiration_at_ms": 1,
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="free"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_plan,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    apply_plan.assert_awaited_once()
    assert apply_plan.await_args.kwargs["plan"] == "free"


def test_revenuecat_webhook_subscriber_fetch_failure_returns_503():
    """HTTP 200 would ack the event and drop a failed REST lookup forever."""
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {"event": {"type": "INITIAL_PURCHASE", "app_user_id": str(uid)}}

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_plan,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 503
    apply_plan.assert_not_awaited()


def test_revenuecat_webhook_customer_support_refund_rechecks_entitlement():
    """CUSTOMER_SUPPORT is a store refund — REST decides whether Pro stays."""
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "CANCELLATION",
            "app_user_id": str(uid),
            "cancel_reason": "CUSTOMER_SUPPORT",
            "expiration_at_ms": 4099689600000,
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="free"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_plan,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    apply_plan.assert_awaited_once()
    assert apply_plan.await_args.kwargs["plan"] == "free"


def test_revenuecat_webhook_customer_support_keeps_pro_when_entitlement_active():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "CANCELLATION",
            "app_user_id": str(uid),
            "cancel_reason": "CUSTOMER_SUPPORT",
            "expiration_at_ms": 4099689600000,
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=False),
        ) as apply_plan,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    apply_plan.assert_awaited_once()
    assert apply_plan.await_args.kwargs["plan"] == "pro"


def test_revenuecat_webhook_billing_issue_does_not_downgrade():
    """BILLING_ISSUE must not instantly set plan=free — wait for EXPIRATION."""
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {"event": {"type": "BILLING_ISSUE", "app_user_id": str(uid)}}

    with patch(
        "app.modules.billing.subscription.apply_plan_for_app_user_id",
        AsyncMock(return_value=True),
    ) as apply_plan:
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    apply_plan.assert_not_awaited()


def test_revenuecat_webhook_expiration_still_downgrades():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {"event": {"type": "EXPIRATION", "app_user_id": str(uid)}}

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="free"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_plan,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    apply_plan.assert_awaited_once()
    assert apply_plan.await_args.kwargs["plan"] == "free"


def test_revenuecat_webhook_ignores_stale_expiration_after_purchase():
    """INITIAL_PURCHASE then older EXPIRATION must not downgrade (plan stays pro)."""
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
        email_enabled=False,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    purchase = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "id": "evt-purchase",
            "app_user_id": str(uid),
            "event_timestamp_ms": 2000,
        }
    }
    stale_expiration = {
        "event": {
            "type": "EXPIRATION",
            "id": "evt-expire",
            "app_user_id": str(uid),
            "event_timestamp_ms": 1000,
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_plan,
        patch(
            "app.modules.billing.subscription.is_stale_rc_event",
            AsyncMock(side_effect=[False, True]),
        ),
        patch(
            "app.modules.billing.subscription.advance_rc_event_watermark",
            AsyncMock(),
        ) as advance,
    ):
        client = TestClient(app)
        assert client.post("/webhooks/revenuecat", json=purchase).status_code == 200
        assert client.post("/webhooks/revenuecat", json=stale_expiration).status_code == 200

    assert apply_plan.await_count == 1
    assert apply_plan.await_args.kwargs["plan"] == "pro"
    advance.assert_awaited_once()
    assert advance.await_args.args[2] == 2000


def test_revenuecat_webhook_newer_expiration_still_applies_after_purchase():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
        email_enabled=False,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    purchase = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "id": "evt-purchase-2",
            "app_user_id": str(uid),
            "event_timestamp_ms": 1000,
        }
    }
    expiration = {
        "event": {
            "type": "EXPIRATION",
            "id": "evt-expire-2",
            "app_user_id": str(uid),
            "event_timestamp_ms": 2000,
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(side_effect=["pro", "free"]),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_plan,
        patch(
            "app.modules.billing.subscription.is_stale_rc_event",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.billing.subscription.advance_rc_event_watermark",
            AsyncMock(),
        ) as advance,
    ):
        client = TestClient(app)
        assert client.post("/webhooks/revenuecat", json=purchase).status_code == 200
        assert client.post("/webhooks/revenuecat", json=expiration).status_code == 200

    assert apply_plan.await_count == 2
    assert apply_plan.await_args_list[0].kwargs["plan"] == "pro"
    assert apply_plan.await_args_list[1].kwargs["plan"] == "free"
    assert [c.args[2] for c in advance.await_args_list] == [1000, 2000]


def test_expiration_overflow_ms_returns_none():
    """Huge expiration_at_ms must not raise (webhook 500 / retry storm)."""
    from app.modules.billing.revenuecat import _expiration

    assert _expiration({"event": {"expiration_at_ms": 10**20}}) is None
    assert _expiration({"event": {"expiration_at_ms": -(10**20)}}) is None


def test_revenuecat_webhook_huge_expiration_still_succeeds():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "app_user_id": str(uid),
            "expiration_at_ms": 10**20,
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()) as enq,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    assert enq.await_args.kwargs.get("expiration") is None


def test_revenuecat_webhook_dedups_replay_by_event_id():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "event_id": "evt_123",
            "app_user_id": str(uid),
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()),
    ):
        client = TestClient(app)
        r1 = client.post("/webhooks/revenuecat", json=payload)
        r2 = client.post("/webhooks/revenuecat", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    apply_mock.assert_awaited_once()


def test_revenuecat_webhook_missing_event_id_hashes_payload_for_dedupe():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "app_user_id": str(uid),
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()),
    ):
        client = TestClient(app)
        r1 = client.post("/webhooks/revenuecat", json=payload)
        r2 = client.post("/webhooks/revenuecat", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    apply_mock.assert_awaited_once()


def test_revenuecat_webhook_pro_event_defers_when_entitlement_unresolved():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "event_id": "evt_unresolved",
            "app_user_id": str(uid),
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 503
    apply_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_revenuecat_webhook_concurrent_deliveries_process_once():
    """Two deliveries of one event at once: the first is held while it owns the
    event, and the second is turned away with 503 having processed nothing."""
    import asyncio

    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "event_id": "evt_race",
            "app_user_id": str(uid),
        }
    }
    first_holds_claim = asyncio.Event()
    finish_first = asyncio.Event()
    resolved: list[int] = []

    async def resolve(*_args, **_kwargs):
        resolved.append(1)
        if len(resolved) == 1:  # only the first delivery is held
            first_holds_claim.set()
            await finish_first.wait()
        return "pro"

    with (
        patch("app.modules.billing.subscription.resolve_plan_from_revenuecat", resolve),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()) as enq,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = asyncio.create_task(client.post("/webhooks/revenuecat", json=payload))
            await asyncio.wait_for(first_holds_claim.wait(), timeout=5)
            r2 = await client.post("/webhooks/revenuecat", json=payload)
            finish_first.set()
            r1 = await first

    assert r1.status_code == 200
    assert r2.status_code == 503
    apply_mock.assert_awaited_once()
    enq.assert_awaited_once()


def test_revenuecat_webhook_failed_processing_does_not_burn_dedup_key():
    """BUG FIX regression: a transient failure while processing an event must
    not mark the event id as seen — otherwise RevenueCat's legitimate retry
    of the same event_id would be silently swallowed by the dedup check,
    permanently losing the plan sync."""
    import fakeredis.aioredis
    import pytest

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "event_id": "evt_retry_1",
            "app_user_id": str(uid),
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(side_effect=[RuntimeError("boom"), True]),
        ) as apply_mock,
    ):
        client = TestClient(app)
        with pytest.raises(RuntimeError):
            client.post("/webhooks/revenuecat", json=payload)

        # The event id must not have been marked as seen by the failed attempt.
        r2 = client.post("/webhooks/revenuecat", json=payload)

    assert r2.status_code == 200
    assert apply_mock.await_count == 2


def test_revenuecat_webhook_requires_auth_in_production():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="production",
        revenuecat_webhook_auth="whsec-secret",
    )
    app.dependency_overrides[get_redis] = lambda: fakeredis.aioredis.FakeRedis(
        decode_responses=True
    )

    payload = {"event": {"type": "INITIAL_PURCHASE", "app_user_id": str(uid)}}

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()),
    ):
        client = TestClient(app)
        r_bad = client.post("/webhooks/revenuecat", json=payload)
        r_ok = client.post(
            "/webhooks/revenuecat",
            json=payload,
            headers={"Authorization": "Bearer whsec-secret"},
        )

    assert r_bad.status_code == 401
    assert r_ok.status_code == 200
    apply_mock.assert_awaited_once()


def test_revenuecat_webhook_ignores_sandbox_in_production():
    """Sandbox INITIAL_PURCHASE must not grant Pro on a production host."""
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="production",
        revenuecat_webhook_auth="whsec-secret",
    )
    app.dependency_overrides[get_redis] = lambda: fakeredis.aioredis.FakeRedis(
        decode_responses=True
    )

    payload = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "app_user_id": str(uid),
            "environment": "SANDBOX",
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()) as enq,
    ):
        client = TestClient(app)
        r = client.post(
            "/webhooks/revenuecat",
            json=payload,
            headers={"Authorization": "Bearer whsec-secret"},
        )

    assert r.status_code == 200
    apply_mock.assert_not_awaited()
    enq.assert_not_awaited()


def test_revenuecat_webhook_processes_sandbox_in_development():
    """Local StoreKit testing still needs the webhook path to mutate plan."""
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    app.dependency_overrides[get_redis] = lambda: fakeredis.aioredis.FakeRedis(
        decode_responses=True
    )

    payload = {
        "event": {
            "type": "INITIAL_PURCHASE",
            "app_user_id": str(uid),
            "environment": "SANDBOX",
        }
    }

    with (
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
        patch("app.modules.billing.api.enqueue_purchase_receipt", AsyncMock()),
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    apply_mock.assert_awaited_once()


def test_revenuecat_webhook_transfer_downgrades_old_and_syncs_new():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    old_uid = uuid4()
    new_uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "TRANSFER",
            "app_user_id": str(new_uid),
            "transferred_from": [str(old_uid)],
        }
    }

    with patch(
        "app.modules.billing.subscription.handle_revenuecat_transfer",
        AsyncMock(),
    ) as transfer_mock:
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 200
    transfer_mock.assert_awaited_once()
    kwargs = transfer_mock.await_args.kwargs
    assert kwargs["new_app_user_id"] == str(new_uid)
    assert kwargs["transferred_from"] == [str(old_uid)]


def test_revenuecat_webhook_transfer_failure_does_not_dedup():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    old_uid = uuid4()
    new_uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "TRANSFER",
            "event_id": "evt_transfer_fail",
            "app_user_id": str(new_uid),
            "transferred_from": [str(old_uid)],
        }
    }

    with patch(
        "app.modules.billing.subscription.handle_revenuecat_transfer",
        AsyncMock(return_value=False),
    ) as transfer_mock:
        client = TestClient(app)
        r1 = client.post("/webhooks/revenuecat", json=payload)
        r2 = client.post("/webhooks/revenuecat", json=payload)

    assert r1.status_code == 503
    assert r2.status_code == 503
    assert transfer_mock.await_count == 2


def test_revenuecat_webhook_malformed_transfer_is_not_deduped():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "TRANSFER",
            "event_id": "evt_transfer_blank",
            "app_user_id": str(uid),
            "original_app_user_id": str(uid),
        }
    }
    # Blank target after strip — ack (nothing to apply) without calling transfer.
    payload["event"]["app_user_id"] = "   "

    with patch(
        "app.modules.billing.subscription.handle_revenuecat_transfer",
        AsyncMock(),
    ) as transfer_mock:
        client = TestClient(app)
        r1 = client.post("/webhooks/revenuecat", json=payload)
        r2 = client.post("/webhooks/revenuecat", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    transfer_mock.assert_not_awaited()


def test_verify_auth_non_ascii_header_is_401():
    from fastapi import HTTPException

    from app.modules.billing.api import _verify_auth

    settings = Settings(revenuecat_webhook_auth="whsec-secret")
    with pytest.raises(HTTPException) as exc:
        _verify_auth("\x80whsec-secret", settings)
    assert exc.value.status_code == 401


def test_revenuecat_webhook_subscriber_lock_busy_returns_503():
    import fakeredis.aioredis

    from app.core.deps import get_redis, get_settings_dep
    from app.modules.billing import api as webhooks_mod

    uid = uuid4()
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis

    payload = {
        "event": {
            "type": "RENEWAL",
            "event_id": "evt_busy",
            "app_user_id": str(uid),
        }
    }

    with (
        patch.object(webhooks_mod, "acquire_lock", AsyncMock(return_value=None)),
        patch(
            "app.modules.billing.subscription.resolve_plan_from_revenuecat",
            AsyncMock(return_value="pro"),
        ),
        patch(
            "app.modules.billing.subscription.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply_mock,
    ):
        client = TestClient(app)
        r = client.post("/webhooks/revenuecat", json=payload)

    assert r.status_code == 503
    apply_mock.assert_not_awaited()
