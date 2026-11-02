"""Shared process bootstrap wiring tests."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import process_bootstrap
from app.core.config import Settings
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected_warmups"),
    [("all", 1), ("api", 1), ("worker", 0)],
)
async def test_initialize_process_warms_sympy_only_for_api_roles(
    role: str,
    expected_warmups: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import shutdown

    monkeypatch.setattr(shutdown, "_callbacks", [])
    warm_sympy = AsyncMock()
    with (
        patch("app.process_bootstrap.setup_logging"),
        patch("app.process_bootstrap.init_sentry"),
        patch("app.process_bootstrap.validate_production_settings"),
        patch("app.process_bootstrap.setup_mcp_adapters"),
        patch("app.process_bootstrap.warmup_db_pool", AsyncMock()),
        patch("app.process_bootstrap.warm_sympy_pool", warm_sympy),
    ):
        await process_bootstrap.initialize_process(
            Settings(mock_llm_enabled=True, process_role=role)
        )

    assert warm_sympy.await_count == expected_warmups
    # Only a process that serves chat stops its turns at the signal.
    from app.modules.chat.finalize_registry import stop_inflight_streams

    assert (stop_inflight_streams in shutdown._callbacks) is bool(expected_warmups)
    if expected_warmups:
        from app.modules.chat.turn_prep.reading import warm_pool_worker

        warm_sympy.assert_awaited_once_with(warm_pool_worker)


@pytest.mark.asyncio
async def test_start_worker_runtime_registers_before_consumer_and_schedulers():
    order: list[str] = []

    def register_all() -> None:
        order.append("register")

    async def start_worker(_settings: Settings) -> None:
        order.append("worker")

    settings = Settings(mock_llm_enabled=True)
    with (
        patch("app.process_bootstrap.job_handlers.register_all", side_effect=register_all),
        patch("app.process_bootstrap.jobs.start_worker", side_effect=start_worker),
        patch(
            "app.process_bootstrap.push_scheduler.start_push_scheduler",
            AsyncMock(),
        ),
        patch(
            "app.process_bootstrap.email_reminder_scheduler.start_email_reminder_scheduler",
            AsyncMock(),
        ),
        patch(
            "app.process_bootstrap.attachment_orphan_reaper.start_orphan_reaper",
            AsyncMock(),
        ),
        patch(
            "app.process_bootstrap.billing_reconcile_scheduler.start_billing_reconcile_scheduler",
            AsyncMock(),
        ),
    ):
        await process_bootstrap.start_worker_runtime(settings)

    assert order == ["register", "worker"]


@pytest.mark.asyncio
async def test_worker_runtime_starts_and_stops_every_scheduler_in_order():
    calls: list[str] = []

    def recorder(name: str) -> AsyncMock:
        return AsyncMock(side_effect=lambda *_args: calls.append(name))

    schedulers = {
        "push": ("push_scheduler", "start_push_scheduler", "stop_push_scheduler"),
        "email": (
            "email_reminder_scheduler",
            "start_email_reminder_scheduler",
            "stop_email_reminder_scheduler",
        ),
        "reaper": ("attachment_orphan_reaper", "start_orphan_reaper", "stop_orphan_reaper"),
        "billing": (
            "billing_reconcile_scheduler",
            "start_billing_reconcile_scheduler",
            "stop_billing_reconcile_scheduler",
        ),
    }
    with ExitStack() as stack:
        stack.enter_context(patch("app.process_bootstrap.job_handlers.register_all"))
        stack.enter_context(
            patch("app.process_bootstrap.jobs.start_worker", recorder("start jobs"))
        )
        stack.enter_context(patch("app.process_bootstrap.jobs.stop_worker", recorder("stop jobs")))
        for name, (module, start, stop) in schedulers.items():
            stack.enter_context(
                patch(f"app.process_bootstrap.{module}.{start}", recorder(f"start {name}"))
            )
            stack.enter_context(
                patch(f"app.process_bootstrap.{module}.{stop}", recorder(f"stop {name}"))
            )
        await process_bootstrap.start_worker_runtime(Settings(mock_llm_enabled=True))
        await process_bootstrap.stop_worker_runtime()

    assert calls == [
        "start jobs",
        "start push",
        "start email",
        "start reaper",
        "start billing",
        "stop jobs",
        "stop push",
        "stop email",
        "stop reaper",
        "stop billing",
    ]


@pytest.mark.asyncio
async def test_shutdown_process_stops_worker_before_closing_resources():
    stop_worker = AsyncMock()
    redis = redis_mock()
    redis.aclose = AsyncMock()
    engine = MagicMock()
    engine.dispose = AsyncMock()
    with (
        patch("app.process_bootstrap.drain_background_tasks", AsyncMock()) as drain,
        patch("app.process_bootstrap.stop_worker_runtime", stop_worker),
        patch("app.process_bootstrap.engine", engine),
        patch("app.process_bootstrap.get_redis_client", return_value=redis),
        patch("app.process_bootstrap.aclose_pooled_clients", AsyncMock()) as close_http,
        patch("app.process_bootstrap.shutdown_sympy_executor") as stop_sympy,
        # The stop flag is process-wide; a real one would refuse later tests' turns.
        patch("app.process_bootstrap.shutdown.begin_stop") as begin_stop,
    ):
        await process_bootstrap.shutdown_process(stop_worker=True)

    begin_stop.assert_called_once_with()
    drain.assert_awaited_once_with(timeout_seconds=10.0)
    stop_worker.assert_awaited_once()
    stop_sympy.assert_called_once_with()
    engine.dispose.assert_awaited_once()
    redis.aclose.assert_awaited_once()
    close_http.assert_awaited_once()
