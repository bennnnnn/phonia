"""Background worker entrypoint — jobs + schedulers without HTTP."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

from app import process_bootstrap
from app.background import periodic
from app.core import jobs
from app.core.config import get_settings
from app.worker_health import create_worker_health_app

logger = logging.getLogger(__name__)

# How often the worker checks that its jobs loop and schedulers still run.
WATCHDOG_INTERVAL_SECONDS = 10.0
# Exit status when a critical loop died. Fly restarts a Machine only when its
# process exits (fly.toml [[restart]] policy "always"); a failing health check
# alone never restarts it, so a worker whose loop died used to idle forever.
EXIT_LOOP_DIED = 1


def dead_loops() -> list[str]:
    """Critical loops that will not run again: the jobs consumer, or a scheduler.

    The jobs consumer counts as dead when its heartbeat is stale too (it never
    waits on a job, so stale means the event loop or the consumer is wedged).
    A scheduler counts only once its task has ended.
    """
    dead = [] if jobs.is_worker_alive() else ["jobs"]
    return dead + periodic.stopped_periodic()


async def wait_for_stop_or_death(stop: asyncio.Event, interval: float) -> list[str]:
    """Wait for ``stop``; return the dead loops instead if any die first."""
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return []
        except TimeoutError:
            dead = dead_loops()
            if dead:
                return dead


async def _run_worker() -> int:
    settings = get_settings()
    await process_bootstrap.initialize_process(settings)
    await process_bootstrap.start_worker_runtime(settings)

    # Tiny health HTTP server: readiness for deploys and uptime monitors.
    health_server = None
    health_task: asyncio.Task | None = None
    if settings.worker_health_port > 0:
        import uvicorn

        health_server = uvicorn.Server(
            uvicorn.Config(
                create_worker_health_app(),
                host="0.0.0.0",  # noqa: S104 - Fly requires binding to all interfaces
                port=settings.worker_health_port,
                log_level="warning",
                access_log=False,
            )
        )
        health_task = asyncio.create_task(health_server.serve())

    # SIGTERM (kill, docker stop, most supervisors) ended the worker on the
    # spot: none of the shutdown below ran, so its jobs consumer stayed in the
    # group and, with PROCESS_ROLE=all, its SymPy workers outlived it. SIGINT
    # (Ctrl+C, Fly's default) already unwinds through the finally.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
        loop.add_signal_handler(signal.SIGTERM, stop.set)

    logger.info("Recall worker started (process_role=worker)")
    try:
        dead = await wait_for_stop_or_death(stop, WATCHDOG_INTERVAL_SECONDS)
        if dead:
            logger.error(
                "Worker loop(s) stopped: %s; exiting so the Machine restarts", ", ".join(dead)
            )
            return EXIT_LOOP_DIED
        return 0
    finally:
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.remove_signal_handler(signal.SIGTERM)
        if health_server is not None:
            health_server.should_exit = True
            await health_server.shutdown()
        if health_task is not None:
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass
        await process_bootstrap.shutdown_process(
            stop_worker=True,
            drain_before_stop=False,
        )


def main() -> None:
    sys.exit(asyncio.run(_run_worker()))


if __name__ == "__main__":
    main()
