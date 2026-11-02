"""WebSocket: account B cannot send to, regenerate, or read account A's chat.

Sync test: Starlette's ``TestClient`` runs the app on its own event loop, so
the rows are seeded and removed with ``asyncio.run`` around it and the engine
pool is dropped between loops.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core import access_tokens

from .conftest import (
    _seed,
    delete_accounts,
    isolated_settings,
    reset_process_caches,
    use_fake_redis,
)


def _frames_until_error(ws: Any) -> list[dict]:
    frames: list[dict] = []
    while True:
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("type") in {"error", "done"}:
            return frames


def test_websocket_turns_on_another_users_chat_are_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.core.db import SessionLocal, engine
    from app.main import create_app
    from app.models.orm import Message

    storage_root = tmp_path / "attachments"
    storage_root.mkdir()
    settings = isolated_settings(monkeypatch, storage_root)

    async def seed():
        await engine.dispose(close=False)
        try:
            return await _seed(settings, storage_root)
        finally:
            await engine.dispose()

    a_id, b_id, data, _b_chat = asyncio.run(seed())
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    use_fake_redis(monkeypatch, fake)
    after: dict[str, Any] = {}
    try:
        token = access_tokens.create_access_token(b_id, settings)
        client = TestClient(create_app())
        with client.websocket_connect(f"/ws/chats/{data.chat_id}") as ws:
            ws.send_json({"token": token})
            ws.send_json({"type": "message", "content": "what is the plan?"})
            sent = _frames_until_error(ws)
            ws.send_json({"type": "regenerate"})
            regenerated = _frames_until_error(ws)
        for frames in (sent, regenerated):
            assert frames[-1] == {
                "type": "error",
                "code": "not_found",
                "message": "Chat not found.",
                "user_message_saved": False,
            }, frames
            assert not any(f.get("type") in {"token", "done", "stream_end"} for f in frames)
            assert data.secret_word not in str(frames)
    finally:

        async def cleanup() -> None:
            await engine.dispose(close=False)
            async with SessionLocal() as session:
                after["count"] = (
                    await session.execute(
                        select(func.count())
                        .select_from(Message)
                        .where(Message.chat_id == data.chat_id)
                    )
                ).scalar()
                after["assistant"] = await session.get(Message, data.assistant_message_id)
            await delete_accounts(a_id, b_id)
            await engine.dispose()

        asyncio.run(cleanup())
        reset_process_caches()

    assert after["count"] == 2
    assert after["assistant"] is not None
