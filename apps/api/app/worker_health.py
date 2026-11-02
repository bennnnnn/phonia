"""Tiny HTTP health server for the standalone worker process.

The worker (`app/worker_main.py`) has no HTTP surface. This exposes a single
`/health/ready` endpoint (on `settings.worker_health_port`) that reports ready
only when Redis is reachable, the job-loop task is alive, AND any started
periodic schedulers (push / email / reaper / billing) have not died or gone
stale. Fly uses it to gate deploys and shows it in `fly checks list` and its
metrics, where an alert can watch it. A failing check does NOT restart the
Machine (Fly restarts only on process exit), so `worker_main` itself exits when
the jobs loop or a scheduler dies. It is NOT mounted on the main API app.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, status

from app.background import periodic
from app.core import jobs
from app.core.redis import get_redis_client

# Answer inside Fly's 5s check timeout (fly.toml) with a clean 503 instead of
# letting a stalled Redis hold the probe for the 5s socket timeout.
READY_REDIS_TIMEOUT_SECONDS = 3.0


def create_worker_health_app() -> FastAPI:
    app = FastAPI(title="Recall Worker Health")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        if not jobs.is_worker_alive():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="worker loop not running",
            )
        unhealthy = periodic.started_periodic_unhealthy()
        if unhealthy:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"periodic loop not running: {', '.join(unhealthy)}",
            )
        try:
            async with asyncio.timeout(READY_REDIS_TIMEOUT_SECONDS):
                await get_redis_client().ping()
        except Exception:
            # Don't leak connection details — just signal not ready.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dependency check failed",
            ) from None
        return {"status": "ok"}

    return app
