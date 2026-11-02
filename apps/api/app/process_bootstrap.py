"""Shared API/worker process initialization and worker runtime wiring."""

import asyncio
from collections.abc import Awaitable, Callable

from app.background import (
    analytics_retention_scheduler,
    billing_reconcile_scheduler,
    data_retention_scheduler,
    email_reminder_scheduler,
    push_scheduler,
)
from app.background import handlers as job_handlers
from app.content.legal import warn_if_no_support_email
from app.core import blocking, jobs, shutdown
from app.core.background_tasks import drain_background_tasks
from app.core.config import Settings, validate_production_settings
from app.core.db import engine, warmup_db_pool
from app.core.document_executor import shutdown_document_executor
from app.core.logging import setup_logging
from app.core.redis import get_jobs_redis_client, get_redis_client
from app.core.saturation import start_saturation_monitor, stop_saturation_monitor
from app.core.sentry import init_sentry
from app.core.sympy_executor import shutdown_sympy_executor, warm_sympy_pool
from app.gateways import email_gateway
from app.gateways.http_client import aclose_pooled_clients
from app.modules.attachments import reaper as attachment_orphan_reaper
from app.modules.chat.finalize_registry import stop_inflight_streams
from app.modules.chat.turn_prep.reading import warm_pool_worker
from app.modules.chat.ws_limits import open_socket_count
from app.services.mcp import setup_mcp_adapters

VALID_PROCESS_ROLES = frozenset({"all", "api", "worker"})

_Start = Callable[[Settings], Awaitable[None]]
_Stop = Callable[[], Awaitable[None]]


def validate_process_role(settings: Settings) -> str:
    role = settings.process_role.strip().lower()
    if role not in VALID_PROCESS_ROLES:
        raise RuntimeError(
            f"Invalid PROCESS_ROLE={settings.process_role!r}; "
            f"expected one of {sorted(VALID_PROCESS_ROLES)}"
        )
    return role


async def initialize_process(settings: Settings) -> None:
    setup_logging(json_output=settings.environment == "production", level=settings.log_level)
    init_sentry(settings)
    validate_production_settings(settings)
    warn_if_no_support_email(settings)
    email_gateway.warn_if_unavailable(settings)
    role = validate_process_role(settings)
    setup_mcp_adapters(settings)
    await warmup_db_pool()
    start_saturation_monitor({"sockets": open_socket_count})
    if role in ("all", "api"):
        await warm_sympy_pool(warm_pool_worker)
        install_chat_stop_on_signal()


def install_chat_stop_on_signal() -> None:
    """At SIGINT/SIGTERM, stop in-flight chat turns the way the user's Stop does.

    uvicorn only runs the lifespan shutdown after its graceful wait; by then the
    machine is about to be killed. Stopped at the signal, each partial reply is
    saved and its chat's prepare lock released inside that wait (deploy: Fly
    ``kill_timeout`` 45s, uvicorn ``--timeout-graceful-shutdown`` 30s).
    """
    shutdown.on_stop(stop_inflight_streams)
    shutdown.install_signal_hook(asyncio.get_running_loop())


def _schedulers() -> tuple[tuple[_Start, _Stop], ...]:
    """Every periodic scheduler the worker runs, as (start, stop), in start order.

    A new scheduler is one row here (its cycle uses ``background.periodic``).
    Read at call time, so each module's functions stay patchable.
    """
    return (
        (push_scheduler.start_push_scheduler, push_scheduler.stop_push_scheduler),
        (
            email_reminder_scheduler.start_email_reminder_scheduler,
            email_reminder_scheduler.stop_email_reminder_scheduler,
        ),
        (attachment_orphan_reaper.start_orphan_reaper, attachment_orphan_reaper.stop_orphan_reaper),
        (
            billing_reconcile_scheduler.start_billing_reconcile_scheduler,
            billing_reconcile_scheduler.stop_billing_reconcile_scheduler,
        ),
        (
            analytics_retention_scheduler.start_analytics_retention_scheduler,
            analytics_retention_scheduler.stop_analytics_retention_scheduler,
        ),
        (
            data_retention_scheduler.start_data_retention_scheduler,
            data_retention_scheduler.stop_data_retention_scheduler,
        ),
    )


async def start_worker_runtime(settings: Settings) -> None:
    job_handlers.register_all()
    await jobs.start_worker(settings)
    for start, _stop in _schedulers():
        await start(settings)


async def stop_worker_runtime() -> None:
    await jobs.stop_worker()
    for _start, stop in _schedulers():
        await stop()


async def shutdown_process(
    *,
    stop_worker: bool,
    drain_before_stop: bool = True,
) -> None:
    # Already done at the signal when the hook is installed; a no-op then.
    shutdown.begin_stop()
    await stop_saturation_monitor()
    if stop_worker and not drain_before_stop:
        await stop_worker_runtime()
    await drain_background_tasks(timeout_seconds=10.0)
    if stop_worker and drain_before_stop:
        await stop_worker_runtime()
    shutdown_sympy_executor()
    shutdown_document_executor()
    blocking.shutdown()
    await engine.dispose()
    await get_redis_client().aclose()
    # The worker's long-poll client (the API never makes one).
    if get_jobs_redis_client.cache_info().currsize:
        await get_jobs_redis_client().aclose()
    await aclose_pooled_clients()
