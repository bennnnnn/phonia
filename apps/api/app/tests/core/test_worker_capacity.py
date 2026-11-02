"""The worker runs many model-bound jobs at once on a small database pool.

Eight job slots per worker meant about 130 workers at launch-scale turn rates, each
with the app's 30-connection pool: thousands of Neon connections. Jobs hold no
connection while they await a model, so the worker runs 32 at once and gets a pool
smaller than its slots.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from app.core.config import Settings

_REPO = Path(__file__).resolve().parents[5]
_FLY = tomllib.loads((_REPO / "fly.toml").read_text())


def _env(command: str, name: str) -> int:
    found = re.search(rf"\b{name}=(\d+)\b", command)
    assert found is not None, f"{name} is not set in {command!r}"
    return int(found.group(1))


def test_worker_runs_32_jobs_at_once_by_default() -> None:
    assert Settings().jobs_worker_concurrency == 32


def test_worker_database_pool_is_bounded_below_its_job_slots() -> None:
    command = _FLY["processes"]["worker"]
    defaults = Settings()
    worker_pool = _env(command, "DB_POOL_SIZE") + _env(command, "DB_MAX_OVERFLOW")
    app_pool = defaults.db_pool_size + defaults.db_max_overflow

    assert "PROCESS_ROLE=worker" in command
    assert worker_pool < defaults.jobs_worker_concurrency
    assert worker_pool < app_pool
