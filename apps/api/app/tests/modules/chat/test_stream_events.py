"""Chat stream_events helpers (finalize wait / done gating)."""

import asyncio

import pytest

from app.modules.chat import stream_events
from app.modules.chat.turn_outcome import TurnOutcome


@pytest.mark.asyncio
async def test_await_finalize_commit_timeout_does_not_cancel_task(monkeypatch: pytest.MonkeyPatch):
    """Bare wait_for would cancel finalize on timeout; shield must keep it alive."""
    gate = asyncio.Event()

    async def slow_finalize() -> None:
        await gate.wait()

    task = asyncio.create_task(slow_finalize())
    monkeypatch.setattr(stream_events, "DONE_COMMIT_WAIT_SECONDS", 0.05)
    status = await stream_events.await_finalize_commit(task)

    assert status == "timeout"
    assert not task.done()

    gate.set()
    await task
    assert task.done()
    assert task.exception() is None


@pytest.mark.asyncio
async def test_await_finalize_commit_returns_false_on_failure():
    async def boom() -> None:
        raise RuntimeError("commit failed")

    task = asyncio.create_task(boom())
    status = await stream_events.await_finalize_commit(task)
    assert status == "failed"


@pytest.mark.asyncio
async def test_await_finalize_commit_returns_committed_on_success():
    async def ok_finalize() -> None:
        return None

    task = asyncio.create_task(ok_finalize())
    status = await stream_events.await_finalize_commit(task)
    assert status == "committed"


@pytest.mark.asyncio
async def test_await_finalize_commit_returns_committed_when_no_task():
    status = await stream_events.await_finalize_commit(None)
    assert status == "committed"


@pytest.mark.asyncio
async def test_persist_finalize_if_pending_awaits_task():
    ran = False

    async def finalize() -> None:
        nonlocal ran
        ran = True

    outcome = TurnOutcome(
        finalize_db_task=asyncio.create_task(finalize()),
        finalize_task=asyncio.create_task(asyncio.sleep(0)),
    )
    await stream_events.persist_finalize_if_pending(outcome)
    assert ran is True
    assert outcome.finalize_db_task is None
    assert outcome.finalize_task is None


@pytest.mark.asyncio
async def test_persist_finalize_if_pending_is_noop_without_task():
    await stream_events.persist_finalize_if_pending(TurnOutcome())


def test_spend_cap_refusal_has_its_own_code():
    from app.exceptions import SpendCapReachedError

    payload = stream_events.error_payload_for_exception(SpendCapReachedError("Paused today."))
    assert payload == {"type": "error", "code": "spend_cap", "message": "Paused today."}


def test_a_pictures_spend_cap_names_its_feature():
    """The phone says the picture is paused, not that every message is."""
    from app.exceptions import SpendCapReachedError

    capped = SpendCapReachedError("Pictures paused.", feature="image_generation")
    payload = stream_events.error_payload_for_exception(capped)
    assert payload == {
        "type": "error",
        "code": "spend_cap",
        "message": "Pictures paused.",
        "feature": "image_generation",
    }


def _turn_failures() -> list[BaseException]:
    from app.exceptions import (
        AttachmentValidationError,
        ChatBusyError,
        ChatNotFoundError,
        ChatServiceError,
        ConsentRequiredError,
        QuotaExceededError,
        RedisUnavailableError,
        SpendCapReachedError,
        TurnRefusedError,
        UnknownModelOverrideError,
    )
    from app.gateways.litellm_gateway import ModelUnavailableError

    return [
        QuotaExceededError("Out of messages."),
        RedisUnavailableError(),
        ChatBusyError(),
        AttachmentValidationError("Too big."),
        UnknownModelOverrideError("x"),
        SpendCapReachedError("Paused today."),
        ConsentRequiredError(),
        TurnRefusedError("No more pictures.", code="daily_limit"),
        ModelUnavailableError("Model down."),
        ChatNotFoundError("Chat not found."),
        ChatServiceError("Could not generate image"),
        RuntimeError("boom"),
    ]


@pytest.mark.parametrize("exc", _turn_failures(), ids=lambda exc: type(exc).__name__)
def test_every_turn_error_frame_names_a_code(exc: BaseException) -> None:
    """The phone words a frame by its code. A chat gone, an image service failure and
    any unexpected error named none, and the phone showed their English."""
    payload = stream_events.error_payload_for_exception(exc)
    assert payload["code"]
    assert payload["message"]


def test_a_failure_with_no_exception_is_failed_unless_it_says_otherwise() -> None:
    assert stream_events.turn_error_payload(None, user_message_saved=False)["code"] == "failed"
    restart = stream_events.turn_error_payload(
        None,
        user_message_saved=False,
        message=stream_events.SERVER_RESTARTING_MESSAGE,
        code=stream_events.SERVER_RESTARTING_CODE,
    )
    assert restart["code"] == "server_restarting"


@pytest.mark.parametrize("saved", [True, False])
def test_turn_error_payload_says_whether_the_user_message_saved(saved: bool):
    from app.exceptions import ChatBusyError

    assert stream_events.turn_error_payload(ChatBusyError(), user_message_saved=saved) == {
        "type": "error",
        "code": "busy",
        "message": "Still generating — wait or cancel first.",
        "user_message_saved": saved,
    }
    assert stream_events.turn_error_payload(
        None, user_message_saved=saved, message=stream_events.REPLY_SAVE_FAILED_MESSAGE
    ) == {
        "type": "error",
        "code": "failed",
        "message": stream_events.REPLY_SAVE_FAILED_MESSAGE,
        "user_message_saved": saved,
    }


@pytest.mark.parametrize(
    ("commit", "expected"),
    [
        ("committed", {"type": "done", "message_id": "m1", "final_content": "hi"}),
        ("timeout", {"type": "done", "final_content": "hi", "persisting": True}),
        (
            "failed",
            {
                "type": "error",
                # Coded: the phone showed the English.
                "code": "reply_not_saved",
                "message": stream_events.REPLY_SAVE_FAILED_MESSAGE,
                "user_message_saved": True,
            },
        ),
    ],
)
def test_settled_turn_event_follows_the_commit(
    commit: stream_events.CommitStatus, expected: dict[str, object]
) -> None:
    outcome = TurnOutcome(message_id="m1", final_content="hi", user_message_saved=True)
    assert stream_events.settled_turn_event(outcome, commit) == expected
