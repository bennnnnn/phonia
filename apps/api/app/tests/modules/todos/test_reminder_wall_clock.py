"""A reminder is at the user's own clock: no offset the model writes, and no server zone, moves it.

"Remind me to call the dentist tomorrow at 9am" for a UTC user came out at 13:00Z
("1:00 PM"): the prompt's example said ``-04:00`` and the model copied it.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any
from uuid import uuid4

import pytest

from app.modules.conversation import chats_repository as chats_repo
from app.modules.todos.prompt_hint import TODO_HINT
from app.modules.todos.reminder_fences import materialize_reminder_fences
from app.repositories import users as users_repo

_CARD = re.compile(r"```reminder_proposal\n(.*?)\n```", re.S)


async def _card_due(session: Any, redis: Any, due_at: str, user_timezone: str) -> str:
    user = await users_repo.create(
        session, email=f"{uuid4()}@example.com", name="T", avatar_url=None, google_sub=str(uuid4())
    )
    chat = await chats_repo.create(session, user_id=user.id, model="free-chat")
    fence = "```reminder\n" + json.dumps({"title": "Call the dentist", "due_at": due_at}) + "\n```"
    text, _ = await materialize_reminder_fences(
        session,
        user_id=user.id,
        chat_id=chat.id,
        assistant_text=f"Here it is.\n{fence}",
        user_timezone=user_timezone,
        user_text="Remind me to call the dentist on October 23, 2030 at 9am",
        redis=redis,
        confirm=True,
    )
    match = _CARD.search(text)
    assert match is not None, text
    return str(json.loads(match.group(1))["items"][0]["due_at"])


@pytest.fixture
def server_in_new_york(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The API's own zone is US Eastern, as on the dev Mac that showed the bug."""
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("due_at", "zone", "expected"),
    [
        # The copied example offset, a Z, and no offset all mean 9am on the user's clock.
        ("2030-10-23T09:00:00-04:00", "UTC", "2030-10-23T09:00:00Z"),
        ("2030-10-23T09:00:00Z", "UTC", "2030-10-23T09:00:00Z"),
        ("2030-10-23T09:00:00", "UTC", "2030-10-23T09:00:00Z"),
        ("2030-10-23T09:00:00Z", "Africa/Nairobi", "2030-10-23T06:00:00Z"),
        ("2030-10-23T09:00:00-04:00", "Asia/Tokyo", "2030-10-23T00:00:00Z"),
        ("2030-10-23T09:00:00", "America/Los_Angeles", "2030-10-23T16:00:00Z"),
    ],
)
async def test_a_reminder_is_at_the_users_own_clock(
    db_session: Any, fake_redis: Any, server_in_new_york: Any, due_at: str, zone: str, expected: str
) -> None:
    assert await _card_due(db_session, fake_redis, due_at, zone) == expected


def test_the_prompt_never_shows_the_model_an_offset_to_copy() -> None:
    assert re.search(r"T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})", TODO_HINT) is None
