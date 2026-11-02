from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.background import billing_reconcile_scheduler
from app.core.config import Settings
from app.tests.fakes import FakeSessionCM


def _rows(by_plan: dict[str, list[UUID]]):
    """list_ids_by_plan over an in-memory table: one page per plan, then empty."""

    async def list_ids_by_plan(_session, *, plan, after_id=None, limit=25):
        ids = by_plan.get(plan, [])
        return [] if after_id is not None else ids[:limit]

    return AsyncMock(side_effect=list_ids_by_plan)


async def _run(by_plan: dict[str, list[UUID]], resolved: dict[str, str | None]):
    session = AsyncMock()
    lock: Any = SimpleNamespace(refresh=AsyncMock(return_value=True))
    settings = Settings(
        revenuecat_secret_key="sk_test",
        billing_reconcile_batch_size=25,
        billing_reconcile_rest_gap_seconds=0,
    )

    async def resolve(_settings, app_user_id):
        return resolved[app_user_id]

    with (
        patch(
            "app.background.billing_reconcile_scheduler.SessionLocal",
            return_value=FakeSessionCM(session),
        ),
        patch(
            "app.background.billing_reconcile_scheduler.users_repo.list_ids_by_plan",
            _rows(by_plan),
        ),
        patch(
            "app.background.billing_reconcile_scheduler.subscription_service.resolve_plan_from_revenuecat",
            AsyncMock(side_effect=resolve),
        ) as resolve_mock,
        patch(
            "app.background.billing_reconcile_scheduler.subscription_service.apply_plan_for_app_user_id",
            AsyncMock(return_value=True),
        ) as apply,
    ):
        await billing_reconcile_scheduler._billing_cycle(settings, lock)
    return resolve_mock, apply


@pytest.mark.asyncio
async def test_billing_cycle_downgrades_pro_user_without_entitlement():
    pro_id = uuid4()
    resolve, apply = await _run({"pro": [pro_id]}, {str(pro_id): "free"})

    resolve.assert_awaited_once()
    apply.assert_awaited_once()
    assert apply.await_args.args[1] == str(pro_id)
    assert apply.await_args.kwargs["plan"] == "free"


@pytest.mark.asyncio
async def test_billing_cycle_checks_plus_rows_too():
    """A lost EXPIRATION on the lower paid plan must lapse it like Pro."""
    plus_id, pro_id = uuid4(), uuid4()
    resolve, apply = await _run(
        {"plus": [plus_id], "pro": [pro_id]},
        {str(plus_id): "free", str(pro_id): "plus"},
    )

    assert resolve.await_count == 2
    applied = {call.args[1]: call.kwargs["plan"] for call in apply.await_args_list}
    assert applied == {str(plus_id): "free", str(pro_id): "plus"}


@pytest.mark.asyncio
async def test_billing_cycle_leaves_matching_plans_alone():
    plus_id = uuid4()
    _resolve, apply = await _run({"plus": [plus_id]}, {str(plus_id): "plus"})
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_billing_cycle_keeps_pro_when_subscriber_fetch_fails():
    pro_id = uuid4()
    _resolve, apply = await _run({"pro": [pro_id]}, {str(pro_id): None})
    apply.assert_not_awaited()


def test_billing_scheduler_disabled_without_secret():
    settings = Settings(billing_reconcile_enabled=True, revenuecat_secret_key="")
    assert billing_reconcile_scheduler._scheduler_enabled(settings) is False
    settings = Settings(billing_reconcile_enabled=True, revenuecat_secret_key="sk")
    assert billing_reconcile_scheduler._scheduler_enabled(settings) is True
