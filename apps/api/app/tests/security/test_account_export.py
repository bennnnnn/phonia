"""GET /auth/me/export holds everything the user gave Recall, and nothing else."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.core.db import SessionLocal
from app.models.orm import Memory, UsageDaily, User

from .conftest import World


@pytest.mark.asyncio
async def test_export_includes_profile_all_memory_and_every_owned_record(world: World) -> None:
    c, a, data = world.client, world.a, world.a_data
    async with SessionLocal() as session:
        user = await session.get(User, a.id)
        assert user is not None
        user.custom_instructions = "Answer like a pirate"
        user.location = "Lisbon"
        user.timezone = "Europe/Lisbon"
        user.job = "Nurse"
        user.age = 41
        # More saved facts than the old 50-row export cap (150 may be active).
        for index in range(60):
            session.add(
                Memory(
                    user_id=a.id,
                    type="preference",
                    topic="preferences",
                    text=f"Preference number {index}",
                    status="active",
                )
            )
        session.add(
            Memory(
                user_id=a.id,
                type="fact",
                topic="notes",
                text="Muted fact",
                status="muted",
            )
        )
        session.add(
            UsageDaily(user_id=a.id, date=date(2026, 10, 14), input_tokens=100, output_tokens=50)
        )
        await session.commit()
    from app.core.user_cache import forget_user

    forget_user(a.id)
    await c.patch(
        f"/chats/{data.chat_id}/messages/{data.assistant_message_id}/feedback",
        json={"feedback": "up"},
        headers=a.headers,
    )
    await c.patch(f"/chats/{data.chat_id}/archive", json={"archived": True}, headers=a.headers)

    response = await c.get("/auth/me/export", headers=a.headers)
    assert response.status_code == 200
    export = response.json()

    profile = export["user"]
    assert profile["custom_instructions"] == "Answer like a pirate"
    assert profile["location"] == "Lisbon"
    assert profile["timezone"] == "Europe/Lisbon"
    assert profile["job"] == "Nurse" and profile["age"] == 41
    assert "google_sub" not in profile

    memories = export["memories"]
    assert len(memories) == 62
    texts = {memory["text"] for memory in memories}
    assert "Muted fact" in texts and f"User is planning {data.secret_word}" in texts
    secret = next(m for m in memories if m["text"].endswith(data.secret_word))
    assert secret["topic"] == data.area_key and secret["status"] == "active"
    assert export["memory_areas"] == [
        {"key": data.area_key, "title": f"Project {data.secret_word}", "summary": ""}
    ]

    [chat] = export["chats"]
    assert chat["archived"] is True
    assert chat["messages"][1]["feedback"] == "up"
    [todo] = export["todos"]
    assert todo["content"] == f"buy {data.secret_word}"
    assert "recurrence_rule" in todo
    names = {item["original_filename"] for item in export["attachments"]}
    assert f"{data.secret_word}.png" in names
    assert [s["text"] for s in export["suggestions"]] == [f"Follow up on {data.secret_word}"]
    assert export["usage"] == [{"day": "2026-10-14", "input_tokens": 100, "output_tokens": 50}]
    assert [device["platform"] for device in export["push_devices"]] == ["ios"]
    assert data.push_token not in response.text
    assert datetime.fromisoformat(export["exported_at"]).tzinfo == UTC
