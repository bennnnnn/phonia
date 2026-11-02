"""Blocking calls run on a bounded pool of their own kind, with the caller's log ids."""

from __future__ import annotations

import asyncio
import threading

from app.core import blocking
from app.core.log_context import bound_log_ids, current_log_ids


async def test_a_call_runs_on_its_kinds_threads_with_the_callers_context() -> None:
    def where() -> tuple[str, str | None]:
        return threading.current_thread().name, current_log_ids().get("user_id")

    with bound_log_ids(user_id="u1"):
        thread, user = await blocking.run_blocking("storage", where)

    assert thread.startswith("storage")
    assert user == "u1"


async def test_a_full_pool_has_no_room_until_a_call_ends() -> None:
    release = threading.Event()
    started = threading.Barrier(3)

    def hold() -> None:
        started.wait(5)
        release.wait(5)

    calls = [asyncio.create_task(blocking.run_blocking("web_search", hold)) for _ in range(2)]
    # The test's own wait for both threads to start (tests may use the default executor).
    await asyncio.to_thread(started.wait, 5)
    assert blocking.has_room("web_search") is False
    assert blocking.running()["web_search"] == 2
    release.set()
    await asyncio.gather(*calls)
    assert blocking.has_room("web_search") is True
