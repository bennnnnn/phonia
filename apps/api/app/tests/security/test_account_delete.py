"""DELETE /auth/me removes everything the account owns: rows, files and Redis."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models.orm import (
    Attachment,
    Chat,
    Memory,
    MemoryArea,
    Message,
    PushToken,
    Suggestion,
    TodoItem,
    User,
)

from .conftest import World


async def _rows_owned_by(user_id) -> dict[str, int]:
    counts = {}
    async with SessionLocal() as session:
        for model in (
            Attachment,
            Chat,
            Memory,
            MemoryArea,
            Message,
            PushToken,
            Suggestion,
            TodoItem,
        ):
            counts[model.__name__] = int(
                (
                    await session.execute(
                        select(func.count()).select_from(model).where(model.user_id == user_id)
                    )
                ).scalar()
                or 0
            )
        counts["User"] = 1 if await session.get(User, user_id) else 0
    return counts


async def _keys_naming(redis, user_id) -> list[str]:
    return sorted([key async for key in redis.scan_iter(match=f"*{user_id}*")])


@pytest.mark.asyncio
async def test_delete_account_leaves_nothing_of_the_user_behind(world: World) -> None:
    from app.background.handlers import _handle_storage_sweep
    from app.core import jobs
    from app.core.jobs import admin
    from app.modules.account import tokens

    c, a, b, data, redis = world.client, world.a, world.b, world.a_data, world.redis
    # What a signed-in, active account leaves in Redis besides the two cards
    # the fixture created: a refresh session, caches with memory and reply
    # text, today's usage, and the follow-up questions under a reply.
    await tokens.issue_token_pair(redis, a.id, world.settings)
    await redis.set(f"memblock:{a.id}", f"User is planning {data.secret_word}")
    await redis.set(f"memquery:{a.id}:0:abc:a", f"User is planning {data.secret_word}")
    await redis.set(f"home:{a.id}:1:UTC:20261015", json.dumps({"overdue": data.secret_word}))
    await redis.set(f"websearch:{a.id}:5:abc", json.dumps({"q": data.secret_word}))
    await redis.set(f"live_tool:{a.id}:abc", json.dumps({"content": data.secret_word}))
    await redis.set(f"usage:{a.id}:2026-10-15", 1234)
    related_key = f"related_prompts:{data.assistant_message_id}"
    await redis.set(related_key, json.dumps([f"More about {data.secret_word}?"]))
    # B's cache must survive A's delete.
    await redis.set(f"memblock:{b.id}", "B's memory")
    # Finished and failed jobs keep the turn's text in the jobs streams.
    a_job = {"user_id": str(a.id), "chat_id": str(data.chat_id), "transcript": data.secret_word}
    b_job = {"user_id": str(b.id), "chat_id": str(world.b_chat_id), "transcript": "B's turn"}
    await jobs.enqueue(redis, "memory", a_job)
    await jobs.enqueue(redis, "memory", b_job)
    await admin._move_to_dlq(redis, "1-0", {"type": "memory", "payload": json.dumps(a_job)}, "x")

    response = await c.delete("/auth/me", headers=a.headers)
    assert response.status_code == 204

    # The worker runs the queued account sweep: it names the replies whose cached
    # follow-up questions it drops (keyed by reply id, so only the rows could find them).
    sweeps = [
        json.loads(fields["payload"])
        for _id, fields in await redis.xrange("recall:jobs")
        if fields.get("type") == "storage_sweep"
    ]
    assert len(sweeps) == 1
    assert str(data.assistant_message_id) in sweeps[0]["reply_ids"]
    await _handle_storage_sweep(world.settings, sweeps[0])

    assert set((await _rows_owned_by(a.id)).values()) == {0}
    assert not (world.storage_root / data.attachment_key).exists()
    assert await redis.exists(related_key) == 0
    leftover = await _keys_naming(redis, a.id)
    # Only the marker that keeps A's already-issued access tokens dead stays.
    assert leftover == [f"revoked_since:{a.id}"], leftover
    assert await redis.get(f"memblock:{b.id}") == "B's memory"
    streams = json.dumps(
        [await redis.xrange(jobs.JOBS_STREAM), await redis.xrange(jobs.JOBS_DLQ_STREAM)]
    )
    assert data.secret_word not in streams
    assert "B's turn" in streams

    # A's old token stops working at once; B is unaffected.
    assert (await c.get("/auth/me", headers=a.headers)).status_code == 401
    assert (await c.get("/auth/me", headers=b.headers)).status_code == 200
