"""The drawer's day groups are worked out in the phone's zone (``client_timezone``).

``GET /chats`` grouped the chats in the profile's zone, which the phone syncs only at
sign-in or when it changes, while the phone puts a chat it inserts itself under a heading
worked out in its own zone. After a flight the two disagreed: in Kathmandu with a UTC
profile, a chat sent five minutes after midnight was listed under Yesterday while the
next one the phone inserted went under Today.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.orm import Chat, User
from app.modules.chat import api as chats_api
from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import messages_repository as messages_repo
from app.repositories import users as users_repo

# 11:45 in Kathmandu, 11:30 in Kolkata, 20:00 in Kiritimati, 03:30 in St. John's.
NOW = datetime(2026, 10, 25, 6, 0, tzinfo=UTC)
# 00:05 on the 25th in Kathmandu, still the 24th in UTC.
JUST_AFTER_KATHMANDU_MIDNIGHT = datetime(2026, 10, 24, 18, 20, tzinfo=UTC)
BUCKETS = ("today", "yesterday", "last_7_days", "this_month", "older")

Client = httpx.AsyncClient
AddChat = Callable[[datetime], Coroutine[Any, Any, Chat]]


class _Clock(datetime):
    """The grouper's ``datetime.now``, held at ``NOW``."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:  # type: ignore[override]
        return NOW.astimezone(tz)


@pytest.fixture
async def user(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> User:
    monkeypatch.setattr(chats_repo, "datetime", _Clock)
    created = await users_repo.create(
        db_session,
        email=f"{uuid4()}@example.com",
        name="Flew East",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    created.timezone = "UTC"
    await db_session.commit()
    return created


@pytest.fixture
def add_chat(db_session: AsyncSession, user: User) -> AddChat:
    async def add(updated_at: datetime) -> Chat:
        chat = await chats_repo.create(db_session, user_id=user.id, model="free-chat")
        await messages_repo.create(
            db_session, chat_id=chat.id, user_id=user.id, role="user", content="hi"
        )
        await db_session.execute(
            update(Chat).where(Chat.id == chat.id).values(updated_at=updated_at)
        )
        await db_session.commit()
        return chat

    return add


@pytest.fixture
async def client(db_session: AsyncSession, user: User) -> AsyncIterator[Client]:
    app = FastAPI()
    app.include_router(chats_api.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def _list(client: Client, params: dict[str, Any], etag: str | None = None) -> httpx.Response:
    return await client.get(
        "/chats", params=params, headers={"If-None-Match": etag} if etag else {}
    )


def _bucket(body: dict[str, Any], chat: Chat) -> str:
    [found] = [key for key in BUCKETS if any(row["id"] == str(chat.id) for row in body[key])]
    return found


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("zone", "updated_at", "in_zone", "in_utc"),
    [
        # +5:45: five minutes after local midnight.
        ("Asia/Kathmandu", JUST_AFTER_KATHMANDU_MIDNIGHT, "today", "yesterday"),
        # +5:30.
        ("Asia/Kolkata", datetime(2026, 10, 24, 18, 35, tzinfo=UTC), "today", "yesterday"),
        # +14, the zone furthest ahead of UTC.
        ("Pacific/Kiritimati", datetime(2026, 10, 24, 10, 5, tzinfo=UTC), "today", "yesterday"),
        # -2:30: five minutes before local midnight, already the next day in UTC.
        ("America/St_Johns", datetime(2026, 10, 25, 2, 25, tzinfo=UTC), "yesterday", "today"),
    ],
)
async def test_list_chats_groups_in_the_phones_zone(
    client: Client, add_chat: AddChat, zone: str, updated_at: datetime, in_zone: str, in_utc: str
) -> None:
    chat = await add_chat(updated_at)
    assert _bucket((await _list(client, {"client_timezone": zone})).json(), chat) == in_zone
    # Without the phone's zone, the profile's (UTC) still decides.
    assert _bucket((await _list(client, {})).json(), chat) == in_utc


@pytest.mark.asyncio
@pytest.mark.parametrize("sent", [None, "", "Not/A/Zone", "../../etc/passwd", "asia/kathmandu"])
async def test_list_chats_falls_back_to_the_profile_zone(
    client: Client, add_chat: AddChat, user: User, db_session: AsyncSession, sent: str | None
) -> None:
    """A missing or unknown name is the profile's zone, never UTC."""
    user.timezone = "Asia/Kathmandu"
    await db_session.commit()
    chat = await add_chat(JUST_AFTER_KATHMANDU_MIDNIGHT)
    response = await _list(client, {} if sent is None else {"client_timezone": sent})
    assert response.status_code == 200
    assert _bucket(response.json(), chat) == "today"


@pytest.mark.asyncio
async def test_list_chats_refuses_a_zone_name_longer_than_a_turn_accepts(client: Client) -> None:
    assert (await _list(client, {"client_timezone": "A" * 65})).status_code == 422


@pytest.mark.asyncio
async def test_a_zone_change_is_never_answered_with_the_old_lists_304(
    client: Client, add_chat: AddChat
) -> None:
    """The ETag hashes the grouped body: another zone's grouping is another body."""
    chat = await add_chat(JUST_AFTER_KATHMANDU_MIDNIGHT)
    in_utc = await _list(client, {})
    landed = await _list(client, {"client_timezone": "Asia/Kathmandu"}, in_utc.headers["etag"])
    again = await _list(client, {"client_timezone": "Asia/Kathmandu"}, landed.headers["etag"])
    assert _bucket(in_utc.json(), chat) == "yesterday"
    assert landed.status_code == 200
    assert _bucket(landed.json(), chat) == "today"
    assert landed.headers["etag"] != in_utc.headers["etag"]
    assert again.status_code == 304


@pytest.mark.asyncio
async def test_the_older_pages_group_in_the_phones_zone_too(
    client: Client, add_chat: AddChat
) -> None:
    """A cursor page joins the first page's headings, so it is grouped in the same zone."""
    await add_chat(NOW - timedelta(hours=1))
    older = await add_chat(JUST_AFTER_KATHMANDU_MIDNIGHT)
    zone = {"client_timezone": "Asia/Kathmandu"}
    first = (await _list(client, {"limit": 1, **zone})).json()
    page = (await _list(client, {"cursor": first["next_cursor"], **zone})).json()
    assert _bucket(page, older) == "today"
