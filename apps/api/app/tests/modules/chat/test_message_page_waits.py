"""A message page waits for the turn in flight only when it can hold that turn's rows.

Scrolling back during a reply used to wait up to 20 s for the reply and its save on
every older page; only a page that reaches the newest row can change when it lands.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.modules.chat import finalize_registry
from app.modules.chat import service as chats
from app.modules.conversation import history as conversation_history
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "anchor, reaches_end, waits, reads",
    [
        ("newest", True, True, 1),
        ("before", False, False, 1),
        ("after", False, False, 1),
        ("after", True, True, 2),
        ("around", False, False, 1),
        ("around", True, True, 2),
    ],
)
async def test_list_messages_page_waits_only_when_it_reaches_the_newest_row(
    anchor, reaches_end, waits, reads
):
    events: list[str] = []

    async def wait_stream(_chat_id):
        events.append("wait")

    async def page_before(*_args, **_kwargs):
        events.append("read")
        return [], False

    async def page_after(*_args, **_kwargs):
        events.append("read")
        return [], not reaches_end

    async def page_around(*_args, **_kwargs):
        events.append("read")
        return [], False, not reaches_end

    anchors = {"newest": {}, "before": {"before": uuid4()}}
    anchors |= {"after": {"after": uuid4()}, "around": {"around": uuid4()}}
    with (
        patch.object(chats, "get_chat", AsyncMock(return_value=SimpleNamespace(title="T"))),
        patch.object(finalize_registry, "wait_for_inflight_stream", side_effect=wait_stream),
        patch.object(finalize_registry, "wait_for_pending_finalize", AsyncMock()),
        patch.object(conversation_history, "messages_page_before", side_effect=page_before),
        patch.object(conversation_history, "messages_after", side_effect=page_after),
        patch.object(conversation_history, "messages_around", side_effect=page_around),
        # The newest page asks Redis for cached follow-up questions; none are cached.
        patch.object(chats, "load_related_prompts", AsyncMock(return_value={})),
    ):
        await chats.list_messages_page(
            AsyncMock(), redis_mock(), SimpleNamespace(id=uuid4()), uuid4(), **anchors[anchor]
        )
    assert ("wait" in events) is waits
    assert events.count("read") == reads
    if anchor == "newest":
        assert events == ["wait", "read"]
    if waits and anchor != "newest":
        assert events == ["read", "wait", "read"]
