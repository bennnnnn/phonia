"""Chat titles: generated after the first reply, scoped to the chat's owner."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.tests.fakes import FakeSessionCM

# ── topic service ──────────────────────────────────────────────────────────────


_OWNER = uuid4()


@pytest.mark.asyncio
async def test_topic_service_skips_when_title_none():
    from app.modules.chat import titles as topic_service

    mock_set = AsyncMock()
    with (
        patch.object(
            topic_service,
            "generate_title",
            AsyncMock(return_value=None),
        ),
        patch("app.modules.conversation.chats_repository.set_title_if_empty", mock_set),
    ):
        await topic_service.generate_chat_title(Settings(), uuid4(), "hi", "hello", user_id=_OWNER)
    mock_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_topic_service_scopes_chat_by_user_id():
    """The atomic title write retains the job owner's scope."""
    from app.modules.chat import titles as topic_service

    other_user_id = uuid4()
    chat_id = uuid4()
    mock_set = AsyncMock(return_value=False)
    session = AsyncMock()

    with (
        patch.object(topic_service, "SessionLocal", side_effect=[FakeSessionCM(session)]),
        patch.object(
            topic_service,
            "generate_title",
            AsyncMock(return_value="Fresh title"),
        ),
        patch("app.modules.conversation.chats_repository.set_title_if_empty", mock_set),
    ):
        await topic_service.generate_chat_title(
            Settings(), chat_id, "hi", "hello", user_id=other_user_id
        )

    mock_set.assert_awaited_once_with(
        session, chat_id, "Fresh title", user_id=other_user_id, commit=False
    )
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_topic_service_saves_when_title_returned():
    from app.modules.chat import titles as topic_service

    mock_set = AsyncMock(return_value=True)
    session = AsyncMock()

    with (
        patch.object(topic_service, "SessionLocal", side_effect=[FakeSessionCM(session)]),
        patch.object(
            topic_service,
            "generate_title",
            AsyncMock(return_value="Cool chat title"),
        ),
        patch("app.modules.conversation.chats_repository.set_title_if_empty", mock_set),
    ):
        await topic_service.generate_chat_title(Settings(), uuid4(), "hi", "hello", user_id=_OWNER)
    mock_set.assert_awaited_once()
    assert mock_set.await_args.kwargs == {"user_id": _OWNER, "commit": False}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_topic_service_rejects_boring_title():
    from app.modules.chat import titles as topic_service

    mock_set = AsyncMock()
    with (
        patch.object(
            topic_service,
            "generate_title",
            AsyncMock(return_value="New chat"),
        ),
        patch("app.modules.conversation.chats_repository.set_title_if_empty", mock_set),
    ):
        await topic_service.generate_chat_title(Settings(), uuid4(), "hi", "hello", user_id=_OWNER)
    mock_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_topic_service_skips_empty_messages():
    from app.modules.chat import titles as topic_service

    with patch.object(
        topic_service,
        "generate_title",
        AsyncMock(return_value="Valid title here"),
    ) as mock_gen:
        await topic_service.generate_chat_title(Settings(), uuid4(), "  ", "hello", user_id=_OWNER)
    mock_gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_topic_service_skips_when_chat_already_titled():
    from app.modules.chat import titles as topic_service

    mock_set = AsyncMock(return_value=False)
    session = AsyncMock()

    with (
        patch.object(topic_service, "SessionLocal", side_effect=[FakeSessionCM(session)]),
        patch.object(
            topic_service,
            "generate_title",
            AsyncMock(return_value="Fresh title"),
        ) as mock_gen,
        patch("app.modules.conversation.chats_repository.set_title_if_empty", mock_set),
    ):
        applied = await topic_service.generate_chat_title(
            Settings(), uuid4(), "hi", "hello", user_id=_OWNER
        )
    mock_gen.assert_awaited_once()
    mock_set.assert_awaited_once()
    # Not applied: the job handler tells the queue it is not done.
    assert applied is False


@pytest.mark.asyncio
async def test_topic_generate_chat_title_releases_db_before_llm():
    from app.modules.chat import titles as topic_service

    session = AsyncMock()
    session.commit = AsyncMock()
    db_open_during_generate: list[bool] = []

    class _TrackingSessionCM(FakeSessionCM):
        def __init__(self) -> None:
            super().__init__(session)
            self.open = False

        async def __aenter__(self) -> AsyncMock:
            self.open = True
            return await super().__aenter__()

        async def __aexit__(self, *args: object) -> bool:
            self.open = False
            return await super().__aexit__(*args)

    apply_cm = _TrackingSessionCM()

    async def fake_generate(*_args: object, **_kwargs: object) -> str:
        db_open_during_generate.append(apply_cm.open)
        return "Generated title"

    with (
        patch.object(topic_service, "SessionLocal", side_effect=[apply_cm]),
        patch.object(
            topic_service,
            "generate_title",
            AsyncMock(side_effect=fake_generate),
        ),
        patch("app.modules.conversation.chats_repository.set_title_if_empty", AsyncMock()),
    ):
        await topic_service.generate_chat_title(Settings(), uuid4(), "hi", "hello", user_id=_OWNER)

    assert db_open_during_generate == [False]
    assert session.commit.await_count == 1
