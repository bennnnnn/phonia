"""Memory edits the user waits on: Redis down at the write lock is 503, a held lock is 409.

``acquire_memory_write_lock`` returned None on a Redis error as when another write held
the lock, so an outage answered 409 ``memory_busy``: the phone said "Memory is being
updated. Try again in a moment." and never checked its connection, which it does after a
503. The lock's own Redis is what fails or holds here, so the real lock code runs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.db import get_db
from app.core.deps import get_current_user
from app.main import create_app
from app.modules.memory import locks
from app.tests.api_support import api_user

_AUTH = {"Authorization": "Bearer tok"}
_UNAVAILABLE = {
    "detail": {
        "code": "unavailable",
        "message": "Service temporarily unavailable. Please retry shortly.",
    }
}

# Every memory change the user makes by hand, each behind the user's write lock.
EDITS: dict[str, Callable[[TestClient], Any]] = {
    "edit a fact": lambda c: c.patch(f"/memories/{uuid4()}", headers=_AUTH, json={"text": "Tea"}),
    "mute a fact": lambda c: c.patch(
        f"/memories/{uuid4()}", headers=_AUTH, json={"status": "muted"}
    ),
    "delete a fact": lambda c: c.delete(f"/memories/{uuid4()}", headers=_AUTH),
    "delete a page": lambda c: c.delete("/memories/documents/preferences", headers=_AUTH),
    "delete everything": lambda c: c.delete("/memories", headers=_AUTH),
    "ask in words": lambda c: c.post(
        "/memories/instruct", headers=_AUTH, json={"instruction": "Remember I like tea"}
    ),
}


@contextmanager
def _client(lock: str) -> Iterator[tuple[TestClient, AsyncMock]]:
    """A signed-in client whose memory write lock is ``down`` (Redis errors) or ``held``."""
    user = api_user(ai_data_consent_at=datetime(2026, 1, 1, tzinfo=UTC))
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    take = AsyncMock(
        side_effect=RedisConnectionError("Error 111 connecting to redis")
        if lock == "down"
        # Another write's lock: SET NX finds the key taken.
        else lambda *_args, **_kwargs: None
    )
    with ExitStack() as stack:
        stack.enter_context(patch.object(redis, "set", take))
        stack.enter_context(patch.object(locks, "get_redis_client", return_value=redis))
        stack.enter_context(patch("app.modules.memory.api.get_redis_client", return_value=redis))
        # Every limit lets it by: only the lock's Redis fails (test_limit_outages.py for those).
        stack.enter_context(
            patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch("app.core.rate_limit.allow_request", AsyncMock(return_value=True))
        )
        yield TestClient(app), take


def _lock_takes(take: AsyncMock) -> int:
    return sum(str(call.args[0]).startswith("memwrite:") for call in take.await_args_list)


@pytest.mark.parametrize("name", EDITS)
def test_a_memory_edit_with_redis_down_answers_503_unavailable(name: str) -> None:
    with _client("down") as (client, take):
        response = EDITS[name](client)
    # Said at once: an outage is not waited out like a held lock.
    assert _lock_takes(take) == 1
    assert response.status_code == 503
    assert response.json() == _UNAVAILABLE
    assert response.headers["retry-after"] == "5"


@pytest.mark.parametrize("name", EDITS)
def test_a_memory_edit_while_another_write_holds_the_lock_is_still_busy(name: str) -> None:
    with _client("held") as (client, take):
        response = EDITS[name](client)
    assert _lock_takes(take) >= 1, "the edit's write lock was not reached"
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "memory_busy"


@pytest.mark.asyncio
async def test_background_writers_still_wait_out_an_outage_as_a_held_lock() -> None:
    """Extraction, consolidation and lesson progress retry a busy lock after a backoff;
    an outage keeps that retry (None), never a failed job."""
    down = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch.object(down, "set", AsyncMock(side_effect=RedisConnectionError("down"))),
        patch.object(locks, "get_redis_client", return_value=down),
    ):
        assert await locks.acquire_memory_write_lock(uuid4()) is None
