"""DELETE /auth/me is complete or refused whole: a failure at any step leaves no half account.

The database failing part-way used to leave the account signed out everywhere with its
files deleted and every other row kept, and the phone read the retry's 401 as "deleted".
Now every row goes in one transaction, before anything outside the database: a failure
there rolls it all back (503 ``unavailable``, still signed in, so the retry deletes it).
Once the rows are gone, a failure ending the sessions, deleting the files or queueing the
sweep never fails the request: the worker's sweep, also scheduled before the commit, does
each again.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import exc as sa_exc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Delete

from .conftest import World
from .test_account_delete import _keys_naming, _rows_owned_by

_UNAVAILABLE = {
    "detail": {
        "code": "unavailable",
        "message": "Service temporarily unavailable. Please retry shortly.",
    }
}


def _db_down() -> sa_exc.OperationalError:
    return sa_exc.OperationalError("DELETE", {}, Exception("server closed the connection"))


@contextmanager
def _db_fails_at(step: str) -> Any:
    """Postgres failing at one step of the delete: a table's DELETE, or the commit of the
    transaction that deleted the chats (the user row goes with it)."""
    real_execute, real_commit = AsyncSession.execute, AsyncSession.commit
    deleted_chats: set[int] = set()

    async def execute(self: AsyncSession, statement: Any, *args: Any, **kwargs: Any) -> Any:
        table = getattr(statement, "table", None) if isinstance(statement, Delete) else None
        if table is not None and table.name == step:
            raise _db_down()
        if table is not None and table.name == "chats":
            deleted_chats.add(id(self))
        return await real_execute(self, statement, *args, **kwargs)

    async def commit(self: AsyncSession) -> None:
        if step == "commit" and id(self) in deleted_chats:
            raise _db_down()
        await real_commit(self)

    with (
        patch.object(AsyncSession, "execute", execute),
        patch.object(AsyncSession, "commit", commit),
    ):
        yield


async def _state(world: World) -> dict[str, Any]:
    """What the account has: its rows, its file, its session and a cached follow-up."""
    data = world.a_data
    return {
        "rows": await _rows_owned_by(world.a.id),
        "file": (world.storage_root / data.attachment_key).exists(),
        "signed_in": (await world.client.get("/auth/me", headers=world.a.headers)).status_code,
        "follow_up": await world.redis.exists(f"related_prompts:{data.assistant_message_id}"),
    }


async def _queued_sweeps(redis: Any) -> list[dict[str, Any]]:
    """Every queued ``storage_sweep`` payload: on the jobs stream, or waiting to run."""
    from app.core.jobs import JOBS_STREAM
    from app.core.jobs.delayed import DELAYED_ZSET

    found = [fields for _id, fields in await redis.xrange(JOBS_STREAM)]
    found += [json.loads(member)["fields"] for member in await redis.zrange(DELAYED_ZSET, 0, -1)]
    sweeps = {"storage_sweep", "account_sweep_backstop"}
    return [json.loads(f["payload"]) for f in found if f.get("type") in sweeps]


async def _run_sweeps(world: World) -> int:
    """The worker runs each queued sweep; one for an account still there skips."""
    from app.background.handlers import _handle_storage_sweep
    from app.core.jobs import JobSkipped

    ran = 0
    for payload in await _queued_sweeps(world.redis):
        try:
            await _handle_storage_sweep(world.settings, payload)
            ran += 1
        except JobSkipped:
            pass
    return ran


async def _assert_gone(world: World) -> None:
    assert set((await _rows_owned_by(world.a.id)).values()) == {0}
    assert not (world.storage_root / str(world.a.id)).exists() or not any(
        (world.storage_root / str(world.a.id)).iterdir()
    )
    assert await world.redis.exists(f"related_prompts:{world.a_data.assistant_message_id}") == 0
    assert await _keys_naming(world.redis, world.a.id) == [f"revoked_since:{world.a.id}"]
    assert (await world.client.get("/auth/me", headers=world.a.headers)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "step",
    # Each table's DELETE in the order the delete runs them, then the commit.
    ["memories", "todo_items", "suggestions", "attachments", "messages", "chats", "commit"],
)
async def test_delete_with_the_database_failing_at_a_step_deletes_nothing_and_retries(
    world: World, step: str
) -> None:
    redis = world.redis
    await redis.set(
        f"related_prompts:{world.a_data.assistant_message_id}", json.dumps(["More?"]), ex=3600
    )
    before = await _state(world)
    assert before["signed_in"] == 200 and before["file"] and before["rows"]["User"] == 1

    with _db_fails_at(step):
        refused = await world.client.delete("/auth/me", headers=world.a.headers)

    assert (refused.status_code, refused.json()) == (503, _UNAVAILABLE)
    # Nothing is deleted, and the account is still signed in for the phone's retry.
    after = await _state(world)
    assert after == before, after
    # The sweep scheduled before the commit finds the account and leaves it alone.
    await _run_sweeps(world)
    assert await _state(world) == before

    assert (await world.client.delete("/auth/me", headers=world.a.headers)).status_code == 204
    assert await _run_sweeps(world) >= 1
    await _assert_gone(world)


def _redis_down(*_args: Any, **_kwargs: Any) -> Any:
    raise RedisConnectionError("Error 111 connecting to redis")


def _storage_down(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("storage unreachable")


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["sessions", "files", "sweep_queue"])
async def test_delete_with_a_purge_failing_after_the_commit_is_finished_by_the_sweep(
    world: World, step: str
) -> None:
    """The rows are gone, so the delete answers 204; what failed outside the database
    (ending the sessions, deleting the files, queueing the sweep) the sweep does."""
    from app.core.jobs import queue
    from app.gateways.storage_gateway import get_storage_gateway
    from app.modules.account import tokens

    redis = world.redis
    await redis.set(
        f"related_prompts:{world.a_data.assistant_message_id}", json.dumps(["More?"]), ex=3600
    )
    if step == "sessions":
        failing = patch.object(tokens, "purge_user_sessions", _redis_down)
    elif step == "files":
        failing = patch.object(
            type(get_storage_gateway(world.settings)), "delete_bytes", _storage_down
        )
    else:
        failing = patch.object(queue, "append_entry", _redis_down)
    with failing:
        response = await world.client.delete("/auth/me", headers=world.a.headers)

    assert response.status_code == 204
    assert set((await _rows_owned_by(world.a.id)).values()) == {0}
    assert await _queued_sweeps(redis), "no sweep is queued to finish the delete"
    if step == "sweep_queue":
        # Only the backstop scheduled before the commit is left, due in ten minutes.
        assert await redis.xlen(queue.JOBS_STREAM) == 0
        await _assert_backstop_due(redis)
    assert await _run_sweeps(world) >= 1
    await _assert_gone(world)


async def _assert_backstop_due(redis: Any) -> None:
    from app.core.jobs.delayed import DELAYED_ZSET
    from app.modules.account.lifecycle import SWEEP_BACKSTOP_SECONDS

    [(member, due)] = await redis.zrange(DELAYED_ZSET, 0, -1, withscores=True)
    assert json.loads(member)["fields"]["type"] == "account_sweep_backstop"
    assert 0 < due - time.time() <= SWEEP_BACKSTOP_SECONDS


def test_delete_backstop_has_its_own_job_type() -> None:
    """A worker from before the existence check runs ``storage_sweep`` unguarded, and the
    backstop may name an account a failed delete kept. A worker holds an entry of a type it
    does not know (docs/ROLLBACK.md), so the backstop has its own, run by the same sweep."""
    from app.background import handlers
    from app.core.jobs import queue
    from app.modules.account import lifecycle

    handlers.register_all()
    assert lifecycle.SWEEP_BACKSTOP_JOB != lifecycle.SWEEP_JOB == "storage_sweep"
    assert queue._HANDLERS[lifecycle.SWEEP_BACKSTOP_JOB] is handlers._handle_storage_sweep
