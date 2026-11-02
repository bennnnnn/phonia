"""Two real accounts in Postgres, signed in through the real auth dependency.

The isolation tests need the rows committed: much of the API opens its own
``SessionLocal`` (streams, attachments, lists), so the savepoint-only
``db_session`` fixture would hide owner A's data from the very code under
test and make every "B gets 404" pass for the wrong reason. Rows are deleted
(cascade) when the test ends.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import httpx
import pytest

from app.core import access_tokens, user_cache
from app.core import redis as core_redis
from app.core.config import Settings, get_settings

# A real 1x1 PNG so content sniffing and thumbnails accept the bytes.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@dataclass
class Account:
    id: UUID
    email: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass
class OwnerData:
    """Everything account A owns that account B will try to reach."""

    chat_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    memory_id: UUID
    memory_topic: str
    area_key: str
    todo_id: UUID
    todo_topic: str
    attachment_id: UUID
    attachment_key: str
    pending_attachment_id: UUID
    suggestion_id: UUID
    push_token: str
    reminder_proposal_id: str
    settings_proposal_id: str
    secret_word: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class World:
    a: Account
    b: Account
    a_data: OwnerData
    b_chat_id: UUID
    settings: Settings
    redis: Any
    storage_root: Path
    client: httpx.AsyncClient


async def _seed(settings: Settings, storage_root: Path) -> tuple[UUID, UUID, OwnerData, UUID]:
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

    secret = f"zanzibar{uuid4().hex[:8]}"
    async with SessionLocal() as session:
        a = User(email=f"a-{uuid4()}@example.com", name="Owner A", google_sub=f"a-{uuid4()}")
        b = User(email=f"b-{uuid4()}@example.com", name="Other B", google_sub=f"b-{uuid4()}")
        session.add_all([a, b])
        await session.flush()

        a_chat = Chat(user_id=a.id, model="free-chat", title=f"A private {secret}")
        b_chat = Chat(user_id=b.id, model="free-chat", title="B chat")
        session.add_all([a_chat, b_chat])
        await session.flush()

        a_user_msg = Message(
            chat_id=a_chat.id, user_id=a.id, role="user", content=f"my {secret} plan"
        )
        session.add(a_user_msg)
        await session.flush()
        a_asst_msg = Message(
            chat_id=a_chat.id,
            user_id=a.id,
            role="assistant",
            model="free-chat",
            content=(
                "Here is a draft.\n\n```email\n"
                + json.dumps({"to": "x@example.com", "subject": "Hi", "body": "Hello"})
                + "\n```"
            ),
        )
        b_msg = Message(chat_id=b_chat.id, user_id=b.id, role="user", content="hello from b")
        session.add_all([a_asst_msg, b_msg])
        await session.flush()

        area_key = f"area:{secret}"
        memory = Memory(
            user_id=a.id,
            type="fact",
            topic=area_key,
            text=f"User is planning {secret}",
            status="active",
        )
        session.add(memory)
        session.add(MemoryArea(user_id=a.id, key=area_key, title=f"Project {secret}"))

        todo_topic = f"List {secret}"
        todo = TodoItem(user_id=a.id, content=f"buy {secret}", topic=todo_topic, sort_order=0)
        session.add(todo)

        att_id = uuid4()
        att_key = f"{a.id}/{att_id}"
        (storage_root / str(a.id)).mkdir(parents=True, exist_ok=True)
        (storage_root / att_key).write_bytes(PNG_BYTES)
        attachment = Attachment(
            id=att_id,
            user_id=a.id,
            message_id=a_user_msg.id,
            storage_key=att_key,
            content_type="image/png",
            size_bytes=len(PNG_BYTES),
            source="upload",
            original_filename=f"{secret}.png",
            verified_at=datetime.now(UTC),
        )
        pending_id = uuid4()
        pending = Attachment(
            id=pending_id,
            user_id=a.id,
            storage_key=f"{a.id}/{pending_id}",
            content_type="image/png",
            size_bytes=len(PNG_BYTES),
            source="upload",
        )
        session.add_all([attachment, pending])

        suggestion = Suggestion(
            user_id=a.id,
            text=f"Follow up on {secret}",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        session.add(suggestion)

        push_token = f"ExponentPushToken[{uuid4().hex}]"
        session.add(
            PushToken(user_id=a.id, expo_push_token=push_token, platform="ios", device_id=None)
        )
        await session.commit()

        data = OwnerData(
            chat_id=a_chat.id,
            user_message_id=a_user_msg.id,
            assistant_message_id=a_asst_msg.id,
            memory_id=memory.id,
            memory_topic=area_key,
            area_key=area_key,
            todo_id=todo.id,
            todo_topic=todo_topic,
            attachment_id=att_id,
            attachment_key=att_key,
            pending_attachment_id=pending_id,
            suggestion_id=suggestion.id,
            push_token=push_token,
            reminder_proposal_id="",
            settings_proposal_id="",
            secret_word=secret,
        )
        return a.id, b.id, data, b_chat.id


async def delete_accounts(*user_ids: UUID) -> None:
    from app.core.db import SessionLocal
    from app.core.user_cache import forget_user
    from app.modules.account import lifecycle

    for user_id in user_ids:
        async with SessionLocal() as session:
            await lifecycle.erase_user_rows(session, user_id)
        forget_user(user_id)


def isolated_settings(monkeypatch: pytest.MonkeyPatch, storage_root: Path) -> Settings:
    from app.gateways import storage_gateway

    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_root))
    monkeypatch.setenv("MOCK_LLM_ENABLED", "true")
    get_settings.cache_clear()
    storage_gateway._gateway_cache = None
    return get_settings()


def use_fake_redis(monkeypatch: pytest.MonkeyPatch, fake: Any) -> None:
    """Every Redis client the app makes (the app's and the jobs stream's) is ``fake``.

    The user cache's publishes too, so a change's new generation is what the
    next request's token check reads (``core/user_cache``).
    """
    core_redis.get_redis_client.cache_clear()
    core_redis.get_jobs_redis_client.cache_clear()
    monkeypatch.setattr(core_redis, "_connect", lambda *_a, **_k: fake)
    monkeypatch.setattr(user_cache, "get_redis_client", lambda: fake)


def reset_process_caches() -> None:
    from app.gateways import storage_gateway

    core_redis.get_redis_client.cache_clear()
    get_settings.cache_clear()
    storage_gateway._gateway_cache = None


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[World]:
    from app.core.db import engine
    from app.main import create_app
    from app.modules.account import settings_proposal
    from app.modules.todos import proposals

    storage_root = tmp_path / "attachments"
    storage_root.mkdir()
    settings = isolated_settings(monkeypatch, storage_root)
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    use_fake_redis(monkeypatch, fake)
    await engine.dispose(close=False)

    a_id, b_id, a_data, b_chat_id = await _seed(settings, storage_root)
    try:
        # Owner A has a reminder card and a settings card waiting for a tap.
        reminder_card = await proposals.propose(
            fake,
            user_id=a_id,
            chat_id=a_data.chat_id,
            writes=[],
            user_timezone="UTC",
        )
        a_data.reminder_proposal_id = json.loads(
            reminder_card.split("\n", 1)[1].rsplit("\n```", 1)[0]
        )["proposal_id"]
        a_data.settings_proposal_id = str(uuid4())
        await settings_proposal.store_proposal(
            fake,
            a_id,
            a_data.settings_proposal_id,
            [settings_proposal.SettingsChange(field="appearance", value="dark")],
        )

        a = Account(
            id=a_id,
            email="",
            token=access_tokens.create_access_token(a_id, settings, session_id=str(uuid4())),
        )
        b = Account(
            id=b_id,
            email="",
            token=access_tokens.create_access_token(b_id, settings, session_id=str(uuid4())),
        )
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield World(
                a=a,
                b=b,
                a_data=a_data,
                b_chat_id=b_chat_id,
                settings=settings,
                redis=fake,
                storage_root=storage_root,
                client=client,
            )
    finally:
        await delete_accounts(a_id, b_id)
        await engine.dispose(close=False)
        await fake.aclose()
        reset_process_caches()


@pytest.fixture
async def linked(
    real_redis: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[Any]:
    """The app on the configured Redis for the carry-over tests (``carry_world.py``); the
    keys of the test's accounts, identities and addresses are deleted after it."""
    from .carry_world import linked_world

    async with linked_world(monkeypatch, tmp_path) as world:
        yield world
