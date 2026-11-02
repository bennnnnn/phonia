"""The turn outcome event's error codes: the phone's list, the server's, and the stream's.

Codes added to the chat stream's error frame (``failed``, ``not_found``,
``server_restarting``, ``reply_not_saved``, ``consent_required``, a picture's
``daily_limit`` and ``content_blocked``) were counted as "other" on both sides. A code a
started turn's frame can carry is a bucket here and on the phone, so the next one cannot
drift again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

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
from app.modules.analytics.service import _ALLOWED_PROPERTIES
from app.modules.chat import stream_events
from app.tests.architecture.boundary_support import MOBILE_ROOT

_TURN_OUTCOME = MOBILE_ROOT / "features" / "chat" / "model" / "turnOutcome.ts"
_SERVER_CODES = _ALLOWED_PROPERTIES["chat_turn_outcome"]["error_code"] - {"none", "other"}


def _phone_codes() -> set[str]:
    source = _TURN_OUTCOME.read_text(encoding="utf-8")
    found = re.search(r"const ERROR_CODES = new Set\(\[(.*?)\]\);", source, re.DOTALL)
    assert found, f"no ERROR_CODES list in {_TURN_OUTCOME}"
    return set(re.findall(r'"([a-z_]+)"', found.group(1)))


def test_the_phone_and_the_server_count_the_same_codes() -> None:
    assert _phone_codes() == _SERVER_CODES


# A started turn's failures (turn_load, turn_resources, turn_intercepts, the model call).
_TURN_FAILURES: list[BaseException] = [
    QuotaExceededError("Out of messages."),
    RedisUnavailableError(),
    ChatBusyError(),
    AttachmentValidationError("Too big."),
    UnknownModelOverrideError("x"),
    SpendCapReachedError("Paused today."),
    SpendCapReachedError("Pictures paused.", feature="image_generation"),
    ConsentRequiredError(),
    # turn_intercepts: a picture's own cap or the provider's refusal.
    TurnRefusedError("No more pictures.", code="daily_limit", feature="image_generation"),
    TurnRefusedError("Blocked.", code="content_blocked", feature="image_generation"),
    ModelUnavailableError("Model down."),
    ChatNotFoundError("Chat not found."),
    ChatServiceError("Could not generate image"),
    RuntimeError("boom"),
]


@pytest.mark.parametrize("exc", _TURN_FAILURES, ids=lambda exc: type(exc).__name__)
def test_every_turn_failure_is_counted_by_its_code(exc: BaseException) -> None:
    code = stream_events.error_payload_for_exception(exc)["code"]
    assert code in _SERVER_CODES


@pytest.mark.parametrize(
    "payload",
    [
        stream_events.restarting_payload(user_message_saved=True),
        stream_events.turn_error_payload(None, user_message_saved=True),
        stream_events.turn_error_payload(
            None, user_message_saved=True, code=stream_events.REPLY_NOT_SAVED_CODE
        ),
    ],
    ids=["server_restarting", "failed", "reply_not_saved"],
)
def test_a_failure_with_no_exception_is_counted_by_its_code(payload: dict[str, object]) -> None:
    assert payload["code"] in _SERVER_CODES


def test_every_code_the_stream_names_is_counted() -> None:
    """A literal code added to the frame builders, not just the cases above."""
    source = Path(stream_events.__file__).read_text(encoding="utf-8")
    literal = set(re.findall(r'"code": "([a-z_]+)"', source))
    constants = set(re.findall(r'^[A-Z_]+_CODE = "([a-z_]+)"$', source, re.MULTILINE))
    assert literal | constants
    assert literal | constants <= _SERVER_CODES
