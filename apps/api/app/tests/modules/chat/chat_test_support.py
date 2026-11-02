from contextlib import ExitStack
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.access_tokens import AccessCheck
from app.core.config import Settings
from app.modules.chat.prompt_builder import PromptStats, fetch_subject, inject_subject_block
from app.modules.chat.turn_deps import ChatTurnDeps, default_deps
from app.modules.chat.turn_prep import ClientGeoContext, TurnPromptBundle
from app.modules.conversation import messages_repository
from app.services.solving import VerifiedSolveBlock
from app.tests.fakes import FakeSessionCM


class Overlay:
    """A real module with a few attributes swapped, seen only through one ``ChatTurnDeps``."""

    def __init__(self, base: Any, **swapped: Any) -> None:
        self._base = base
        self.__dict__.update(swapped)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


def access_for(user_id: UUID) -> AccessCheck:
    """What ``check_access`` returns for a live token (any generation will do)."""
    return AccessCheck(user_id=user_id, user_generation="test-generation")


def signed_in(user_id: UUID) -> Any:
    """The WebSocket's token check passes for ``user_id``: one patch for every socket test."""
    return patch(
        "app.modules.chat.ws_api.access_tokens.check_access",
        AsyncMock(return_value=access_for(user_id)),
    )


def ws_streams(stream: Any) -> Any:
    """The WebSocket's message turns run ``stream`` in place of the chat stream."""
    return patch("app.modules.chat.ws_api.stream_entry.stream_chat_response", stream)


def grant_quota() -> AsyncMock:
    """A ``reserve_usage_up_to`` with room for every turn: it takes all it is asked for."""
    return AsyncMock(side_effect=lambda _redis, _user_id, wanted, **_kwargs: wanted)


def turn_deps(**fields: Any) -> ChatTurnDeps:
    """``default_deps()`` with fields swapped for fakes.

    A dict keeps the real module and swaps only the names it lists:
    ``turn_deps(quota={"refund_usage": refund})``.
    """
    base = default_deps()
    swapped: dict[str, Any] = {
        name: Overlay(getattr(base, name), **value) if isinstance(value, dict) else value
        for name, value in fields.items()
    }
    return replace(base, **swapped)


async def augment_subject(
    prompt_messages: list[dict[str, str]],
    user_content: str,
    settings: Settings,
    **fetch_kwargs: Any,
) -> tuple[list[dict[str, str]], VerifiedSolveBlock | None]:
    """Fetch the subject block, then inject it, as a turn's Phase B/C does."""
    fetched = await fetch_subject(user_content, settings, **fetch_kwargs)
    return inject_subject_block(prompt_messages, fetched.subject_block), fetched.verified


def system_prompt(messages: list[dict[str, Any]]) -> str:
    """A built prompt's system text as one: its stable message, the turn's rules, then
    the context and contracts beside the user turn."""
    stable, turn = messages[0], messages[1]
    assert stable["role"] == turn["role"] == "system", (stable["role"], turn["role"])
    return "\n\n".join(
        message["content"]
        for message in messages
        if message["role"] == "system" and isinstance(message["content"], str)
    )


def prompt_bundle(**fields: Any) -> TurnPromptBundle:
    """What a stubbed prompt build returns: an empty prompt unless ``fields`` say otherwise."""
    base: dict[str, Any] = {
        "prompt_messages": [],
        "stats": PromptStats(),
        "instant_reply": None,
        "local_places": False,
        "max_out": 100,
        "fallback_models": [],
        "lightweight": False,
        "rich_context": True,
        "geo": ClientGeoContext(None, None, None, False, False, False, False),
        "local_tz": "UTC",
    }
    return TurnPromptBundle(**{**base, **fields})


def stub_recent(n: int) -> list[MagicMock]:
    """n chronological rows so prior_count can come from list_recent, not COUNT."""
    rows: list[MagicMock] = []
    for i in range(n):
        row = MagicMock()
        row.id = uuid4()
        row.role = "user" if i % 2 == 0 else "assistant"
        row.content = f"m{i}"
        rows.append(row)
    return rows


def offline_session_patches():
    return (
        patch("app.modules.attachments.rag.SessionLocal", FakeSessionCM),
        patch("app.modules.chat.prompt_context.SessionLocal", FakeSessionCM),
        patch("app.modules.chat.turn_prep.attachments.SessionLocal", FakeSessionCM),
        patch("app.modules.chat.turn_prep.context.SessionLocal", FakeSessionCM),
        patch("app.modules.chat.turn_prep.instant.SessionLocal", FakeSessionCM),
        patch("app.modules.chat.turn_prep.persist.SessionLocal", FakeSessionCM),
        patch("app.modules.chat.turn_prep.vision.SessionLocal", FakeSessionCM),
    )


def offline_deps(**fields: Any) -> ChatTurnDeps:
    """The turn's own sessions offline, as ``stream_offline_io`` keeps the rest."""
    return turn_deps(session_factory=FakeSessionCM, **fields)


@pytest.fixture
def stream_offline_io():
    with ExitStack() as stack:
        for patcher in offline_session_patches():
            stack.enter_context(patcher)
        stack.enter_context(patch("app.modules.chat.turn_settle.seed_usage_from_db", AsyncMock()))
        stack.enter_context(patch("app.services.quota.refund_usage", AsyncMock()))
        stack.enter_context(
            patch.object(messages_repository, "list_recent", AsyncMock(return_value=[]))
        )
        stack.enter_context(
            patch("app.modules.chat.turn_load.wait_for_pending_finalize", AsyncMock())
        )
        stack.enter_context(
            patch("app.modules.web_search.is_short_letter_answer", return_value=False)
        )
        yield
