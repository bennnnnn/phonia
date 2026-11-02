"""Tests for the standalone worker entrypoint."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.worker_main import EXIT_LOOP_DIED, _run_worker, dead_loops, wait_for_stop_or_death


@pytest.mark.asyncio
async def test_run_worker_uses_shared_bootstrap():
    settings = Settings(
        mock_llm_enabled=True,
        environment="development",
        worker_health_port=0,
    )
    initialize = AsyncMock()
    start = AsyncMock()
    shutdown = AsyncMock()
    with (
        patch("app.worker_main.get_settings", return_value=settings),
        patch("app.worker_main.process_bootstrap.initialize_process", initialize),
        patch("app.worker_main.process_bootstrap.start_worker_runtime", start),
        patch("app.worker_main.process_bootstrap.shutdown_process", shutdown),
        patch("app.worker_main.wait_for_stop_or_death", AsyncMock(return_value=[])),
    ):
        await _run_worker()

    initialize.assert_awaited_once_with(settings)
    start.assert_awaited_once_with(settings)
    shutdown.assert_awaited_once_with(
        stop_worker=True,
        drain_before_stop=False,
    )


@pytest.mark.asyncio
async def test_run_worker_starts_health_server_when_port_set():
    settings = Settings(
        mock_llm_enabled=True,
        environment="development",
        worker_health_port=8001,
    )
    fake_server = MagicMock()
    fake_server.serve = AsyncMock()
    fake_server.shutdown = AsyncMock()
    fake_config = MagicMock()
    with (
        patch("app.worker_main.get_settings", return_value=settings),
        patch("app.worker_main.process_bootstrap.initialize_process", AsyncMock()),
        patch("app.worker_main.process_bootstrap.start_worker_runtime", AsyncMock()),
        patch("app.worker_main.process_bootstrap.shutdown_process", AsyncMock()),
        patch("app.worker_main.wait_for_stop_or_death", AsyncMock(return_value=[])),
        patch("uvicorn.Server", return_value=fake_server) as server_ctor,
        patch("uvicorn.Config", return_value=fake_config) as config_ctor,
    ):
        await _run_worker()

    assert config_ctor.call_args.kwargs["port"] == 8001
    server_ctor.assert_called_once_with(fake_config)
    fake_server.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_worker_shuts_down_on_sigterm():
    """SIGTERM used to end the worker without running its shutdown."""
    import asyncio
    import os
    import signal

    settings = Settings(
        mock_llm_enabled=True,
        environment="development",
        worker_health_port=0,
    )
    received: list[int] = []
    previous = signal.signal(signal.SIGTERM, lambda sig, _frame: received.append(sig))

    async def started(_settings):
        asyncio.get_running_loop().call_later(0.05, os.kill, os.getpid(), signal.SIGTERM)

    shutdown = AsyncMock()
    try:
        with (
            patch("app.worker_main.get_settings", return_value=settings),
            patch("app.worker_main.process_bootstrap.initialize_process", AsyncMock()),
            patch("app.worker_main.process_bootstrap.start_worker_runtime", started),
            patch("app.worker_main.process_bootstrap.shutdown_process", shutdown),
        ):
            await asyncio.wait_for(_run_worker(), timeout=5)
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert received == []  # the worker handled it, not the stand-in handler
    shutdown.assert_awaited_once_with(stop_worker=True, drain_before_stop=False)


@pytest.mark.parametrize("status", [0, 1])
def test_worker_main_exits_with_the_run_status(status):
    with patch("app.worker_main._run_worker", AsyncMock(return_value=status)) as run_worker:
        from app.worker_main import main

        with pytest.raises(SystemExit) as exited:
            main()
    assert exited.value.code == status
    run_worker.assert_awaited_once()


@pytest.mark.parametrize(
    "jobs_alive, stopped, expected",
    [
        (True, [], []),
        (False, [], ["jobs"]),
        (True, ["push"], ["push"]),
        (False, ["email_reminders"], ["jobs", "email_reminders"]),
    ],
)
def test_dead_loops_names_the_jobs_consumer_and_ended_schedulers(jobs_alive, stopped, expected):
    with (
        patch("app.worker_main.jobs.is_worker_alive", return_value=jobs_alive),
        patch("app.worker_main.periodic.stopped_periodic", return_value=stopped),
    ):
        assert dead_loops() == expected


@pytest.mark.asyncio
async def test_run_worker_exits_nonzero_when_a_loop_dies():
    """Redis down at boot (or any crash) ended the jobs loop while the process
    idled on: Fly restarts a Machine only when its process exits, so jobs
    stopped until someone restarted the worker by hand."""
    settings = Settings(mock_llm_enabled=True, environment="development", worker_health_port=0)
    shutdown = AsyncMock()
    with (
        patch("app.worker_main.get_settings", return_value=settings),
        patch("app.worker_main.process_bootstrap.initialize_process", AsyncMock()),
        patch("app.worker_main.process_bootstrap.start_worker_runtime", AsyncMock()),
        patch("app.worker_main.process_bootstrap.shutdown_process", shutdown),
        patch("app.worker_main.WATCHDOG_INTERVAL_SECONDS", 0.01),
        patch("app.worker_main.dead_loops", side_effect=[[], ["jobs"]]),
    ):
        status = await asyncio.wait_for(_run_worker(), timeout=5)

    assert status == EXIT_LOOP_DIED
    shutdown.assert_awaited_once_with(stop_worker=True, drain_before_stop=False)


@pytest.mark.asyncio
async def test_wait_for_stop_or_death_returns_nothing_on_a_clean_stop():
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.02, stop.set)
    with patch("app.worker_main.dead_loops", return_value=[]):
        assert await wait_for_stop_or_death(stop, 0.005) == []
