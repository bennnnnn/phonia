"""Account B can never read, change, delete, download or stream account A's data.

Both accounts are real rows, signed in with real access tokens through the
real app (middleware, auth dependency, routers). Each route family checks
that B is answered exactly as for an id that does not exist (404, or the
route's usual "not found" answer), and that A's data is untouched afterwards.
"""

from __future__ import annotations

import json
from uuid import uuid4

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


def _sse_events(body: str) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


async def _count(model, *where) -> int:
    async with SessionLocal() as session:
        return int(
            (await session.execute(select(func.count()).select_from(model).where(*where))).scalar()
            or 0
        )


async def _get(model, row_id):
    async with SessionLocal() as session:
        return await session.get(model, row_id)


# ── chats and messages ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_routes_answer_404_for_another_users_chat(world: World) -> None:
    c, a, b, data = world.client, world.a, world.b, world.a_data
    chat = data.chat_id
    msg = data.assistant_message_id
    email = {"to": "evil@example.com", "subject": "pwned", "body": "pwned"}

    attempts = [
        ("GET", f"/chats/{chat}", None),
        ("PATCH", f"/chats/{chat}", {"title": "pwned"}),
        ("PATCH", f"/chats/{chat}/pin", {"pinned": True}),
        ("PATCH", f"/chats/{chat}/archive", {"archived": True}),
        ("GET", f"/chats/{chat}/messages", None),
        ("GET", f"/chats/{chat}/messages?before={msg}", None),
        ("PATCH", f"/chats/{chat}/messages/{msg}/feedback", {"feedback": "down"}),
        ("PATCH", f"/chats/{chat}/messages/{msg}/email", email),
        # A's message id under B's own chat is still not B's message.
        ("PATCH", f"/chats/{world.b_chat_id}/messages/{msg}/feedback", {"feedback": "down"}),
        ("PATCH", f"/chats/{world.b_chat_id}/messages/{msg}/email", email),
        ("DELETE", f"/chats/{chat}", None),
    ]
    for method, path, body in attempts:
        response = await c.request(method, path, json=body, headers=b.headers)
        missing = await c.request(
            method, path.replace(str(chat), str(uuid4())), json=body, headers=b.headers
        )
        assert response.status_code == 404, (method, path, response.text)
        assert response.status_code == missing.status_code, (method, path)

    # Bulk routes only ever touch the caller's own chats.
    assert (await c.post("/chats/archive-all", headers=b.headers)).status_code == 204
    assert (await c.delete("/chats", headers=b.headers)).status_code == 204
    listed = (await c.get("/chats", headers=b.headers)).json()
    assert str(chat) not in json.dumps(listed)

    owner_view = await c.get(f"/chats/{chat}", headers=a.headers)
    assert owner_view.status_code == 200
    assert owner_view.json()["title"].startswith("A private")
    assert owner_view.json()["pinned"] is False
    assert owner_view.json()["archived"] is False
    messages = (await c.get(f"/chats/{chat}/messages", headers=a.headers)).json()["messages"]
    assert [m["id"] for m in messages] == [str(data.user_message_id), str(msg)]
    assert messages[1]["feedback"] is None
    assert "evil@example.com" not in messages[1]["content"]


@pytest.mark.asyncio
async def test_sse_send_and_regenerate_on_another_users_chat_fail_closed(world: World) -> None:
    c, b, data = world.client, world.b, world.a_data
    before = await _count(Message, Message.chat_id == data.chat_id)

    sent = await c.post(
        f"/chats/{data.chat_id}/messages/stream",
        json={"content": "tell me the plan"},
        headers=b.headers,
    )
    regen = await c.post(
        f"/chats/{data.chat_id}/regenerate/stream", json={"content": ""}, headers=b.headers
    )

    for response in (sent, regen):
        events = _sse_events(response.text)
        # Refused before any row is read: the frame says nothing of the chat.
        assert events[-1] == {
            "type": "error",
            "code": "not_found",
            "message": "Chat not found.",
            "user_message_saved": False,
        }, events
        assert not any(e["type"] in {"token", "done", "stream_end"} for e in events), events
        assert data.secret_word not in response.text
    assert await _count(Message, Message.chat_id == data.chat_id) == before
    # Regenerate must not have deleted or replaced A's last assistant reply.
    assert await _get(Message, data.assistant_message_id) is not None
    assert await _count(Message, Message.user_id == world.b.id) == 1


@pytest.mark.asyncio
async def test_sending_another_users_attachment_id_is_refused(world: World) -> None:
    c, b, data = world.client, world.b, world.a_data
    response = await c.post(
        f"/chats/{world.b_chat_id}/messages/stream",
        json={"content": "describe this", "attachment_ids": [str(data.attachment_id)]},
        headers=b.headers,
    )
    events = _sse_events(response.text)
    assert events[-1]["code"] == "attachment_rejected", events
    row = await _get(Attachment, data.attachment_id)
    assert row is not None and row.user_id == world.a.id
    assert row.message_id == data.user_message_id
    assert await _count(Attachment, Attachment.user_id == b.id) == 0


# ── memory ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_routes_answer_404_for_another_users_memory(world: World) -> None:
    c, a, b, data = world.client, world.a, world.b, world.a_data
    mem = data.memory_id
    for method, path, body in [
        ("PATCH", f"/memories/{mem}", {"text": "pwned"}),
        ("PATCH", f"/memories/{mem}", {"status": "muted"}),
        ("DELETE", f"/memories/{mem}", None),
        ("DELETE", f"/memories/documents/{data.area_key}", None),
    ]:
        response = await c.request(method, path, json=body, headers=b.headers)
        assert response.status_code == 404, (method, path, response.text)

    assert (await c.delete("/memories", headers=b.headers)).status_code == 204
    b_list = (await c.get("/memories", headers=b.headers)).json()
    b_docs = (await c.get("/memories/documents", headers=b.headers)).json()
    assert data.secret_word not in json.dumps(b_list)
    assert data.secret_word not in json.dumps(b_docs)

    row = await _get(Memory, mem)
    assert row is not None and row.text.endswith(data.secret_word) and row.status == "active"
    assert await _count(MemoryArea, MemoryArea.user_id == a.id) == 1
    a_docs = (await c.get("/memories/documents", headers=a.headers)).json()
    assert data.secret_word in json.dumps(a_docs)


# ── to-dos and reminder cards ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_todo_routes_never_touch_another_users_items(world: World) -> None:
    c, a, b, data = world.client, world.a, world.b, world.a_data
    todo = data.todo_id
    assert (
        await c.patch(f"/todos/{todo}", json={"checked": True}, headers=b.headers)
    ).status_code == 404
    assert (await c.delete(f"/todos/{todo}", headers=b.headers)).status_code == 404
    linked = await c.post(
        "/todos", json={"content": "x", "chat_id": str(data.chat_id)}, headers=b.headers
    )
    assert linked.status_code == 400
    assert data.secret_word not in (await c.get("/todos/page", headers=b.headers)).text

    row = await _get(TodoItem, todo)
    assert row is not None and row.checked is False
    assert row.sort_order == 0 and row.topic == data.todo_topic
    assert data.secret_word in (await c.get("/todos/page", headers=a.headers)).text


@pytest.mark.asyncio
async def test_reminder_card_of_another_user_cannot_be_confirmed(world: World) -> None:
    c, b, data = world.client, world.b, world.a_data
    pid = data.reminder_proposal_id
    theirs = await c.post(f"/todos/proposals/{pid}/confirm", headers=b.headers)
    nothing = await c.post(f"/todos/proposals/{uuid4()}/confirm", headers=b.headers)
    assert theirs.status_code == nothing.status_code == 410
    # B's attempt did not consume A's card.
    assert await world.redis.exists(f"todos:proposal:{world.a.id}:{pid}") == 1


@pytest.mark.asyncio
async def test_settings_card_of_another_user_cannot_be_confirmed(world: World) -> None:
    c, b, data = world.client, world.b, world.a_data
    pid = data.settings_proposal_id
    path = "/auth/me/settings-proposals/{}/confirm"
    theirs = await c.post(path.format(pid), headers=b.headers)
    nothing = await c.post(path.format(uuid4()), headers=b.headers)
    assert theirs.status_code == nothing.status_code
    assert theirs.json() == nothing.json()
    assert await world.redis.exists(f"settings:proposal:{world.a.id}:{pid}") == 1


# ── attachments ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_attachment_routes_answer_404_for_another_users_file(world: World) -> None:
    c, a, b, data = world.client, world.a, world.b, world.a_data
    att = data.attachment_id
    for method, path in [
        ("GET", f"/attachments/{att}/file"),
        ("GET", f"/attachments/{att}/file?w=64"),
        ("GET", f"/attachments/{att}/url"),
        ("POST", f"/attachments/{att}/confirm"),
        ("DELETE", f"/attachments/{att}"),
        ("POST", f"/attachments/{data.pending_attachment_id}/confirm"),
        ("DELETE", f"/attachments/{data.pending_attachment_id}"),
    ]:
        response = await c.request(method, path, headers=b.headers)
        assert response.status_code == 404, (method, path, response.text)
    upload = await c.put(
        f"/attachments/{data.pending_attachment_id}/upload",
        content=b"\x89PNG\r\n\x1a\n",
        headers={**b.headers, "Content-Type": "image/png"},
    )
    assert upload.status_code == 404
    listed = await c.get("/attachments", headers=b.headers)
    assert str(att) not in listed.text and data.secret_word not in listed.text
    avatar = await c.patch(
        "/auth/me", json={"avatar_url": f"/attachments/{att}/file"}, headers=b.headers
    )
    assert avatar.status_code == 400

    assert (world.storage_root / data.attachment_key).is_file()
    assert await _get(Attachment, data.pending_attachment_id) is not None
    owner_file = await c.get(f"/attachments/{att}/file", headers=a.headers)
    assert owner_file.status_code == 200 and owner_file.content.startswith(b"\x89PNG")


# ── suggestions, push tokens, search, home, export ───────────────────────────


@pytest.mark.asyncio
async def test_the_retired_suggestions_routes_are_gone(world: World) -> None:
    """No route reads or dismisses suggestions any more; stored rows stay only for
    the data export and account deletion until the table is dropped."""
    c, b, data = world.client, world.b, world.a_data
    assert (await c.get("/suggestions", headers=b.headers)).status_code == 404
    response = await c.post(f"/suggestions/{data.suggestion_id}/dismiss", headers=b.headers)
    assert response.status_code == 404
    row = await _get(Suggestion, data.suggestion_id)
    assert row is not None and row.dismissed is False


@pytest.mark.asyncio
async def test_push_token_of_another_user_cannot_be_removed_or_taken(world: World) -> None:
    c, a, b, data = world.client, world.a, world.b, world.a_data
    body = {"expo_push_token": data.push_token, "platform": "ios"}
    removed = await c.request("DELETE", "/users/push-token", json=body, headers=b.headers)
    assert removed.status_code == 204
    taken = await c.post("/users/push-token", json=body, headers=b.headers)
    assert taken.status_code == 403
    async with SessionLocal() as session:
        owners = (
            (
                await session.execute(
                    select(PushToken.user_id).where(PushToken.expo_push_token == data.push_token)
                )
            )
            .scalars()
            .all()
        )
    assert owners == [a.id]


async def _push_token_rows(token: str) -> list[tuple[object, str | None]]:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(PushToken.user_id, PushToken.device_id).where(PushToken.expo_push_token == token)
        )
        return [(user_id, device_id) for user_id, device_id in rows.all()]


@pytest.mark.asyncio
async def test_push_token_without_device_id_cannot_move_to_another_account(world: World) -> None:
    # A's row predates device ids. Knowing the token string and naming any
    # device must not move it (and A's reminders) to B.
    c, a, b, data = world.client, world.a, world.b, world.a_data
    body = {"expo_push_token": data.push_token, "platform": "ios", "device_id": "b-device"}
    taken = await c.post("/users/push-token", json=body, headers=b.headers)
    assert taken.status_code == 403
    assert await _push_token_rows(data.push_token) == [(a.id, None)]

    # A re-registering the same token still works, and records the device.
    again = await c.post(
        "/users/push-token",
        json={**body, "device_id": "a-device"},
        headers=a.headers,
    )
    assert again.status_code == 204
    assert await _push_token_rows(data.push_token) == [(a.id, "a-device")]


@pytest.mark.asyncio
async def test_push_token_with_device_id_moves_only_on_the_same_device(world: World) -> None:
    c, a, b, data = world.client, world.a, world.b, world.a_data
    body = {"expo_push_token": data.push_token, "platform": "ios", "device_id": "a-device"}
    assert (await c.post("/users/push-token", json=body, headers=a.headers)).status_code == 204

    other_device = await c.post(
        "/users/push-token", json={**body, "device_id": "b-device"}, headers=b.headers
    )
    assert other_device.status_code == 403
    assert await _push_token_rows(data.push_token) == [(a.id, "a-device")]

    # The same install signing into B (account switch on one phone) still moves it.
    same_device = await c.post("/users/push-token", json=body, headers=b.headers)
    assert same_device.status_code == 204
    assert await _push_token_rows(data.push_token) == [(b.id, "a-device")]


@pytest.mark.asyncio
async def test_search_and_export_only_show_the_callers_data(world: World) -> None:
    c, a, b, data = world.client, world.a, world.b, world.a_data
    found_b = await c.get("/search", params={"q": data.secret_word}, headers=b.headers)
    assert found_b.status_code == 200 and found_b.json()["items"] == []
    found_a = await c.get("/search", params={"q": data.secret_word}, headers=a.headers)
    assert len(found_a.json()["items"]) >= 1

    export_b = await c.get("/auth/me/export", headers=b.headers)
    assert export_b.status_code == 200
    payload = export_b.json()
    assert data.secret_word not in export_b.text
    assert str(a.id) not in export_b.text
    assert [chat["title"] for chat in payload["chats"]] == ["B chat"]
    export_a = await c.get("/auth/me/export", headers=a.headers)
    assert data.secret_word in export_a.text and "hello from b" not in export_a.text


# ── images, voice, sessions ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_image_generation_into_another_users_chat_is_404(world: World) -> None:
    c, b, data = world.client, world.b, world.a_data
    async with SessionLocal() as session:
        row = await session.get(User, b.id)
        assert row is not None
        row.plan = "pro"
        await session.commit()
    from app.core.user_cache import forget_user

    forget_user(b.id)
    into_their_chat = await c.post(
        "/images/generate",
        json={"chat_id": str(data.chat_id), "prompt": "a cat"},
        headers=b.headers,
    )
    assert into_their_chat.status_code == 404
    their_reference = await c.post(
        "/images/generate",
        json={
            "chat_id": str(world.b_chat_id),
            "prompt": "a cat",
            "reference_attachment_ids": [str(data.attachment_id)],
        },
        headers=b.headers,
    )
    assert their_reference.status_code == 404
    assert await _count(Message, Message.chat_id == data.chat_id) == 2


@pytest.mark.asyncio
async def test_live_talk_routes_refuse_another_users_chat(world: World) -> None:
    c, b, data = world.client, world.b, world.a_data
    async with SessionLocal() as session:
        row = await session.get(User, b.id)
        assert row is not None
        row.plan = "pro"
        await session.commit()
    from app.core.user_cache import forget_user

    forget_user(b.id)
    session_resp = await c.post(
        "/speech/live/session", json={"chat_id": str(data.chat_id)}, headers=b.headers
    )
    assert session_resp.status_code == 404
    persisted = await c.post(
        "/speech/live/persist",
        json={
            "chat_id": str(data.chat_id),
            "call_id": "call-" + uuid4().hex,
            "user_text": "remember my bank pin",
            "assistant_text": "ok",
        },
        headers=b.headers,
    )
    assert persisted.status_code == 403
    tool = await c.post(
        "/speech/live/tool",
        json={
            "chat_id": str(data.chat_id),
            "call_id": "call-" + uuid4().hex,
            "turn_id": "t1",
            "name": "memory_lookup",
            "query": "what is the plan",
        },
        headers=b.headers,
    )
    assert tool.status_code == 403
    assert data.secret_word not in tool.text
    assert await _count(Message, Message.chat_id == data.chat_id) == 2


@pytest.mark.asyncio
async def test_session_of_another_user_cannot_be_revoked(world: World) -> None:
    from app.modules.account import tokens

    c, a, b = world.client, world.a, world.b
    _access, refresh = await tokens.issue_token_pair(world.redis, a.id, world.settings)
    [a_session] = await tokens.list_sessions(world.redis, a.id, current_session_id=None)
    response = await c.delete(f"/auth/sessions/{a_session['id']}", headers=b.headers)
    assert response.status_code == 404
    assert await world.redis.exists(f"refresh:{refresh}") == 1


@pytest.mark.asyncio
async def test_chat_rows_still_belong_to_their_owner(world: World) -> None:
    """Sanity check for the fixture itself: B really is a different account."""
    assert world.a.id != world.b.id
    row = await _get(Chat, world.a_data.chat_id)
    assert row is not None and row.user_id == world.a.id
