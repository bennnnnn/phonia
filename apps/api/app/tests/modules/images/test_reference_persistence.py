from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.conversation import messages_repository
from app.modules.images.generation import ImageGenerationError, generate_for_chat
from app.services.quota import counters
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
@pytest.mark.parametrize("regenerate,fail_write", [(False, False), (False, True), (True, False)])
async def test_image_reference_persistence_is_atomic_and_regeneration_reuses_input(
    regenerate, fail_write
):
    user = SimpleNamespace(id=uuid4())
    reference_id, output_id, chat_id = uuid4(), uuid4(), uuid4()
    # A photo the user attached: not a picture already in the chat.
    source = SimpleNamespace(id=reference_id, content_type="image/png", message_id=None)
    prior = SimpleNamespace(
        id=uuid4(), content=f"Make it blue\n[Image: /attachments/{reference_id}/file]"
    )
    assistant = SimpleNamespace(id=uuid4())
    session = AsyncMock()
    session.__aenter__.return_value = session
    gateway = AsyncMock()
    gateway.presign_upload.return_value = SimpleNamespace(
        attachment_id=str(output_id), storage_key="generated-output"
    )
    generated = AsyncMock(return_value=(b"png", "image/png"))
    load = AsyncMock(return_value=[(source, b"reference-bytes")])
    create = AsyncMock(side_effect=[assistant] if regenerate else [prior, assistant])
    add_image = AsyncMock(side_effect=RuntimeError("insert failed") if fail_write else None)
    refund = AsyncMock()
    with (
        patch("app.modules.images.generation.SessionLocal", return_value=session),
        patch("app.modules.images.generation.can_use", return_value=True),
        patch("app.modules.images.generation.history.get_chat", AsyncMock(return_value=object())),
        patch(
            "app.modules.images.generation.history.last_user_message",
            AsyncMock(return_value=prior),
        ),
        patch("app.modules.images.generation.get_storage_gateway", return_value=gateway),
        patch("app.modules.images.generation.get_redis_client", return_value=redis_mock()),
        patch("app.modules.images.generation.load_reference_images", load),
        patch(
            "app.modules.images.generation.counters.reserve",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.images.generation.counters.refund", refund),
        patch("app.modules.images.generation.generate_image", generated),
        patch("app.modules.images.generation.bytes_match_claimed", return_value=True),
        patch("app.modules.images.generation.attachments_service.add_server_images", add_image),
        patch(
            "app.modules.images.generation.attachments_service.add_reference_copies", AsyncMock()
        ) as copies,
        patch(
            "app.modules.images.generation.attachments_service.list_for_message_ids",
            AsyncMock(return_value=[]),
        ),
        patch.object(messages_repository, "create", create),
        patch(
            "app.modules.images.generation.history.message_count",
            AsyncMock(return_value=0),
        ),
        patch("app.modules.images.generation.finish_turn", AsyncMock()) as finish,
    ):
        args = dict(
            user=user,
            chat_id=chat_id,
            prompt="Make it blue",
            create_user_message=not regenerate,
            reference_attachment_ids=None if regenerate else [reference_id],
        )
        if fail_write:
            with pytest.raises(RuntimeError, match="insert failed"):
                await generate_for_chat(Settings(), **args)
            session.commit.assert_not_awaited()
            assert gateway.delete_bytes.await_count == 2
            refund.assert_awaited_once()
        else:
            await generate_for_chat(Settings(), **args)
            session.commit.assert_awaited_once()
            gateway.delete_bytes.assert_not_awaited()
        assert load.await_args.kwargs["attachment_ids"] == [reference_id]
        assert generated.await_args.kwargs["reference_images"] == [
            (b"reference-bytes", "image/png")
        ]
        assert add_image.await_args.kwargs["message_id"] == assistant.id
        assert all(call.kwargs["commit"] is False for call in create.await_args_list)
        assert copies.await_count == int(not regenerate)
        # A new turn sets off a typed turn's jobs once it is saved; a regenerate does not.
        assert finish.await_count == int(not regenerate and not fail_write)
        if not regenerate:
            assert copies.await_args.kwargs["message_id"] == prior.id
            assert [copy.source for copy in copies.await_args.kwargs["copies"]] == [source]


@pytest.mark.asyncio
async def test_generate_for_chat_refunds_on_cancelled_error():
    """Hard cancel (CancelledError) must refund — except Exception would miss it."""
    import asyncio

    user = SimpleNamespace(id=uuid4())
    chat_id = uuid4()
    refund = AsyncMock()
    session = AsyncMock()
    session.__aenter__.return_value = session
    gateway = AsyncMock()

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise asyncio.CancelledError()

    with (
        patch("app.modules.images.generation.SessionLocal", return_value=session),
        patch("app.modules.images.generation.can_use", return_value=True),
        patch(
            "app.modules.images.generation.history.get_chat",
            AsyncMock(return_value=object()),
        ),
        patch("app.modules.images.generation.get_storage_gateway", return_value=gateway),
        patch("app.modules.images.generation.get_redis_client", return_value=redis_mock()),
        patch("app.modules.images.generation.load_reference_images", AsyncMock(return_value=[])),
        patch(
            "app.modules.images.generation.counters.reserve",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.images.generation.counters.refund", refund),
        patch("app.modules.images.generation.generate_image", boom),
    ):
        with pytest.raises(asyncio.CancelledError):
            await generate_for_chat(
                Settings(),
                user=user,
                chat_id=chat_id,
                prompt="a cat",
            )
    refund.assert_awaited_once()


@pytest.mark.parametrize("next_day_uses", [0, 1])
@pytest.mark.asyncio
async def test_generate_for_chat_refunds_the_day_it_reserved(
    fake_redis, quota_clock, next_day_uses
):
    """A generation reserved before UTC midnight that fails after it refunds the first day."""
    user = SimpleNamespace(id=uuid4(), plan="pro")
    settings = Settings(daily_image_generations_pro=5)
    session = AsyncMock()
    session.__aenter__.return_value = session

    async def fails_after_midnight(*_args: object, **_kwargs: object) -> None:
        quota_clock.day = quota_clock.next_day
        for _ in range(next_day_uses):
            assert await counters.reserve("image_generation", fake_redis, user, settings)
        raise RuntimeError("provider down")

    with (
        patch("app.modules.images.generation.SessionLocal", return_value=session),
        patch("app.modules.images.generation.can_use", return_value=True),
        patch(
            "app.modules.images.generation.history.get_chat",
            AsyncMock(return_value=object()),
        ),
        patch("app.modules.images.generation.get_storage_gateway", return_value=AsyncMock()),
        patch("app.modules.images.generation.get_redis_client", return_value=fake_redis),
        patch("app.modules.images.generation.load_reference_images", AsyncMock(return_value=[])),
        patch("app.modules.images.generation.generate_image", fails_after_midnight),
    ):
        with pytest.raises(RuntimeError, match="provider down"):
            await generate_for_chat(settings, user=user, chat_id=uuid4(), prompt="a cat")
    keys = [f"imggen:{user.id}:2026-10-{n}" for n in (16, 17)]
    assert await fake_redis.mget(keys) == ["0", str(next_day_uses) if next_day_uses else None]


@pytest.mark.asyncio
async def test_generate_for_chat_skips_reserve_when_spend_capped():
    user = SimpleNamespace(id=uuid4())
    chat_id = uuid4()
    reserve = AsyncMock()
    session = AsyncMock()
    session.__aenter__.return_value = session
    gateway = AsyncMock()

    with (
        patch("app.modules.images.generation.SessionLocal", return_value=session),
        patch("app.modules.images.generation.can_use", return_value=True),
        patch(
            "app.modules.images.generation.history.get_chat",
            AsyncMock(return_value=object()),
        ),
        patch("app.modules.images.generation.get_storage_gateway", return_value=gateway),
        patch("app.modules.images.generation.get_redis_client", return_value=redis_mock()),
        patch("app.modules.images.generation.load_reference_images", AsyncMock(return_value=[])),
        patch(
            "app.modules.images.generation.quota_service.global_spend_exceeded",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.images.generation.counters.reserve", reserve),
    ):
        with pytest.raises(ImageGenerationError, match="temporarily unavailable"):
            await generate_for_chat(
                Settings(daily_global_spend_usd=1.0),
                user=user,
                chat_id=chat_id,
                prompt="a cat",
            )
    reserve.assert_not_awaited()


def _patched_generation(
    *,
    source: SimpleNamespace,
    created: list[SimpleNamespace],
    prior: SimpleNamespace | None = None,
    reply: SimpleNamespace | None = None,
    linked: list[SimpleNamespace] | None = None,
):
    """generate_for_chat with storage, quota and provider stubbed out."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    gateway = AsyncMock()
    gateway.presign_upload.return_value = SimpleNamespace(
        attachment_id=str(uuid4()), storage_key="generated-output"
    )
    load = AsyncMock(return_value=[(source, b"reference-bytes")])

    async def create(_session, **kwargs):
        row = SimpleNamespace(id=uuid4(), **kwargs)
        created.append(row)
        return row

    async def get_in_chat(_session, message_id, _chat_id):
        return reply if reply is not None and message_id == reply.id else None

    patches = (
        patch("app.modules.images.generation.SessionLocal", return_value=session),
        patch("app.modules.images.generation.can_use", return_value=True),
        patch("app.modules.images.generation.history.get_chat", AsyncMock(return_value=object())),
        patch(
            "app.modules.images.generation.history.last_user_message",
            AsyncMock(return_value=prior),
        ),
        patch("app.modules.images.generation.history.message_in_chat", get_in_chat),
        patch.object(messages_repository, "create", create),
        patch("app.modules.images.generation.get_storage_gateway", return_value=gateway),
        patch("app.modules.images.generation.get_redis_client", return_value=redis_mock()),
        patch("app.modules.images.generation.load_reference_images", load),
        patch(
            "app.modules.images.generation.counters.reserve",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.images.generation.generate_image",
            AsyncMock(return_value=(b"png", "image/png")),
        ),
        patch("app.modules.images.generation.bytes_match_claimed", return_value=True),
        patch("app.modules.images.generation.attachments_service.add_server_images", AsyncMock()),
        patch(
            "app.modules.images.generation.attachments_service.add_reference_copies", AsyncMock()
        ),
        patch(
            "app.modules.images.generation.attachments_service.list_for_message_ids",
            AsyncMock(return_value=linked or []),
        ),
        patch("app.modules.images.generation.history.message_count", AsyncMock(return_value=2)),
        patch("app.modules.images.generation.finish_turn", AsyncMock()),
    )
    return patches, load


async def _run(patches, **kwargs) -> None:
    from contextlib import ExitStack

    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        user = cast(User, SimpleNamespace(id=uuid4()))
        await generate_for_chat(Settings(), user=user, **kwargs)


@pytest.mark.asyncio
async def test_an_edit_of_the_picture_above_is_not_repeated_in_the_users_bubble() -> None:
    # "Create a cat image" → a cat; "Black" edits that cat. The bubble says
    # "Black", not the cat again, and the copy is still linked for regenerate.
    reply = SimpleNamespace(id=uuid4(), role="assistant")
    cat = SimpleNamespace(id=uuid4(), content_type="image/png", message_id=reply.id)
    created: list[SimpleNamespace] = []
    patches, load = _patched_generation(source=cat, created=created, reply=reply)
    await _run(
        patches,
        chat_id=uuid4(),
        prompt="a cat, black",
        user_message_content="Black",
        reference_attachment_ids=[cat.id],
    )

    user_row, assistant_row = created
    assert user_row.role == "user"
    assert user_row.content == "Black"
    assert assistant_row.content.startswith("[Image: /attachments/")
    assert load.await_args.kwargs["attachment_ids"] == [cat.id]


@pytest.mark.asyncio
async def test_a_photo_the_user_attached_stays_in_their_bubble() -> None:
    photo = SimpleNamespace(id=uuid4(), content_type="image/jpeg", message_id=None)
    created: list[SimpleNamespace] = []
    patches, _load = _patched_generation(source=photo, created=created)
    await _run(
        patches,
        chat_id=uuid4(),
        prompt="make it black and white",
        user_message_content="Make it black and white",
        reference_attachment_ids=[photo.id],
    )

    user_row = created[0]
    assert user_row.content.startswith("Make it black and white\n[Image: /attachments/")


@pytest.mark.asyncio
async def test_a_picture_from_another_chat_stays_in_the_users_bubble() -> None:
    # Picked from the Library: the user brought it here, so it is shown.
    elsewhere = SimpleNamespace(id=uuid4(), content_type="image/png", message_id=uuid4())
    created: list[SimpleNamespace] = []
    patches, _load = _patched_generation(source=elsewhere, created=created)
    await _run(
        patches,
        chat_id=uuid4(),
        prompt="a dog in this style",
        user_message_content="A dog in this style",
        reference_attachment_ids=[elsewhere.id],
    )

    assert "[Image: /attachments/" in created[0].content


@pytest.mark.asyncio
async def test_regenerate_reuses_a_reference_kept_out_of_the_bubble() -> None:
    hidden = SimpleNamespace(id=uuid4(), content_type="image/png", message_id=None, created_at=None)
    prior = SimpleNamespace(id=uuid4(), content="Black")
    created: list[SimpleNamespace] = []
    patches, load = _patched_generation(
        source=hidden, created=created, prior=prior, linked=[hidden]
    )
    await _run(
        patches,
        chat_id=uuid4(),
        prompt="a cat, black",
        create_user_message=False,
    )

    assert load.await_args.kwargs["attachment_ids"] == [hidden.id]
    assert [row.role for row in created] == ["assistant"]
