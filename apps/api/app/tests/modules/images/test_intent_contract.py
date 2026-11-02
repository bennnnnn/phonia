"""The contract for ``POST /images/intent``: the one reader of composer image intent.

The phone reads no image intent; before a send that might be a picture it asks
this endpoint, which answers with the chat turn's own reading (``images.intent``)
of the text and the chat's recent turns. ``docs/fixtures/image_intent_cases.json``
is the server's case list: ``phrases``, ``threads`` and ``revision_contexts`` pin
the word rules, and ``composer`` pins the verdict the endpoint returns.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_current_user, get_settings_dep
from app.main import create_app
from app.models.orm import User
from app.modules.images.gen_intent import extract_image_gen_prompt
from app.modules.images.gen_intent_thread import (
    extract_image_revision_prompt,
    image_gen_revision_context,
)
from app.modules.images.intent import image_gen_request, reads_thread
from app.modules.images.lookup_intent import extract_image_lookup_query

FIXTURE = Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "image_intent_cases.json"
CASES: dict[str, Any] = json.loads(FIXTURE.read_text())
PREVIOUS_SUBJECT: str = CASES["revise_previous_subject"]
THREADS: dict[str, list[dict[str, Any]]] = CASES["composer_threads"]
AFTER_PICTURE = THREADS["after_picture"]


def _id(case: dict[str, Any]) -> str:
    return repr(case["text"])[:60]


def _rows(messages: list[dict[str, Any]]) -> list[SimpleNamespace]:
    return [SimpleNamespace(**{"id": uuid4(), "model": None, **message}) for message in messages]


def _user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.plan = "free"
    return user


@contextmanager
def _client(
    user: User,
    *,
    messages: list[dict[str, Any]] | None = None,
    owned: bool = True,
    settings: Settings | None = None,
) -> Iterator[tuple[TestClient, AsyncMock, AsyncMock]]:
    """A signed-in client whose chat holds ``messages``; ``owned=False`` is someone else's."""
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: settings or Settings()
    get_chat = AsyncMock(return_value=MagicMock() if owned else None)
    list_recent = AsyncMock(return_value=_rows(messages or []))
    with (
        patch("app.modules.images.intent.chat_history.get_chat", get_chat),
        patch("app.modules.images.intent.chat_history.recent_messages", list_recent),
    ):
        yield TestClient(app), get_chat, list_recent


def _verdict(
    text: str,
    messages: list[dict[str, Any]] | None = None,
    *,
    attached: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    with _client(_user(), messages=messages, settings=settings) as (client, _get_chat, _recent):
        response = client.post(
            "/images/intent",
            headers={"Authorization": "Bearer tok"},
            json={"text": text, "chat_id": str(uuid4()), "image_attached": attached},
        )
    assert response.status_code == 200, response.text
    return response.json()


# ── The word rules ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", CASES["phrases"], ids=_id)
def test_intent_contract_phrase(case: dict[str, Any]) -> None:
    text = case["text"]
    assert extract_image_gen_prompt(text) == case["generate"]
    assert extract_image_lookup_query(text) == case["lookup"]
    assert (
        extract_image_revision_prompt(
            text,
            last_assistant_is_image_only=True,
            previous_subject=PREVIOUS_SUBJECT,
        )
        == case["revise"]
    )


@pytest.mark.parametrize("case", CASES["threads"], ids=_id)
def test_intent_contract_thread(case: dict[str, Any]) -> None:
    rows = _rows([{"role": "user", "content": prior} for prior in case["priors"]])
    request = image_gen_request(case["text"], rows)
    assert (request.prompt if request else None) == case["generate"]


@pytest.mark.parametrize("case", CASES["revision_contexts"])
def test_intent_contract_revision_context(case: dict[str, Any]) -> None:
    assert image_gen_revision_context(case["messages"]) == (
        case["last_assistant_is_image_only"],
        case["previous_subject"],
    )


@pytest.mark.parametrize(
    "case",
    [*CASES["threads"], *({"text": c["text"], "priors": []} for c in CASES["phrases"])],
    ids=_id,
)
def test_reads_thread_only_skips_history_that_cannot_change_the_answer(
    case: dict[str, Any],
) -> None:
    """The chat turn reads no history when ``reads_thread`` says so; the answer is the same."""
    text = case["text"]
    rows = _rows([{"role": "user", "content": prior} for prior in case["priors"]] + AFTER_PICTURE)
    if not reads_thread(text):
        assert image_gen_request(text, rows) == image_gen_request(text, [])


# ── The endpoint ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", CASES["composer"], ids=_id)
def test_intent_contract_composer(case: dict[str, Any]) -> None:
    verdict = _verdict(case["text"], THREADS[case["thread"]], attached=case.get("attached", False))
    assert verdict == {
        "subject": case.get("subject"),
        "lookup_query": case.get("lookup"),
        "generate_prompt": case.get("generate"),
        "revision": case.get("revision", False),
        "reference_attachment_ids": case.get("reference", []),
    }


def test_intent_requires_sign_in() -> None:
    client = TestClient(create_app())
    assert client.post("/images/intent", json={"text": "draw me a cat"}).status_code == 401


@pytest.mark.parametrize(
    "text, subject, prompt",
    [
        ("draw ethanol", "chemistry", None),
        ("A lens has focal length 15 cm. Where's the image?", "physics", None),
        ("draw me a cat", None, "cat"),
        ("Generate an image of a lighthouse", None, "a lighthouse"),
    ],
)
def test_intent_answers_a_phone_that_sends_only_text(
    text: str, subject: str | None, prompt: str | None
) -> None:
    """Phones before ES-05 send ``{text}`` and read ``subject``; that still works, unread."""
    with _client(_user()) as (client, get_chat, list_recent):
        response = client.post(
            "/images/intent", headers={"Authorization": "Bearer tok"}, json={"text": text}
        )
    assert response.status_code == 200
    assert response.json()["subject"] == subject
    assert response.json()["generate_prompt"] == prompt
    get_chat.assert_not_awaited()
    list_recent.assert_not_awaited()


def test_intent_leaves_a_structure_to_the_picture_when_chemistry_is_off() -> None:
    verdict = _verdict("draw ethanol", settings=Settings(chemistry_enabled=False))
    assert verdict["subject"] is None
    assert verdict["generate_prompt"] == "ethanol"


def test_intent_looks_no_photo_up_when_image_search_is_off() -> None:
    verdict = _verdict("show me an ear", settings=Settings(image_search_enabled=False))
    assert verdict["lookup_query"] is None
    assert verdict["generate_prompt"] is None


@pytest.mark.parametrize("whose", ["someone else's", "nobody's"])
def test_intent_reads_no_chat_but_the_users_own(whose: str) -> None:
    """A chat that is someone else's, or nobody's, is not found, and none of its turns are read."""
    user, owner = _user(), _user()
    owned_chat = uuid4()

    async def get_by_id(_session: Any, chat_id: UUID, user_id: UUID) -> MagicMock | None:
        return MagicMock() if (chat_id, user_id) == (owned_chat, owner.id) else None

    chat_id = owned_chat if whose == "someone else's" else uuid4()
    with _client(user, messages=AFTER_PICTURE) as (client, get_chat, list_recent):
        get_chat.side_effect = get_by_id
        response = client.post(
            "/images/intent",
            headers={"Authorization": "Bearer tok"},
            json={"text": "make it blue", "chat_id": str(chat_id)},
        )
    assert response.status_code == 404
    assert response.json() == {"detail": "Chat not found"}
    get_chat.assert_awaited_once()
    list_recent.assert_not_awaited()


def test_intent_reads_the_recent_window_of_the_users_chat() -> None:
    user = _user()
    chat_id = uuid4()
    with _client(user, messages=AFTER_PICTURE) as (client, get_chat, list_recent):
        response = client.post(
            "/images/intent",
            headers={"Authorization": "Bearer tok"},
            json={"text": "make it blue", "chat_id": str(chat_id)},
        )
    assert response.status_code == 200
    chat_call, recent_call = get_chat.await_args, list_recent.await_args
    assert chat_call is not None and recent_call is not None
    assert chat_call.args[1:] == (chat_id, user.id)
    assert recent_call.args[1] == chat_id
    assert recent_call.kwargs == {"limit": Settings().recent_message_window}
    assert response.json()["reference_attachment_ids"] == [
        str(UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
    ]


def test_intent_reads_a_draft_chat_as_an_empty_thread() -> None:
    """A draft chat has no id yet: "make it blue" edits nothing, "Image" names nothing."""
    with _client(_user(), messages=AFTER_PICTURE) as (client, get_chat, list_recent):
        for text in ("make it blue", "Image"):
            response = client.post(
                "/images/intent", headers={"Authorization": "Bearer tok"}, json={"text": text}
            )
            assert response.status_code == 200
            assert response.json()["generate_prompt"] is None
    get_chat.assert_not_awaited()
    list_recent.assert_not_awaited()


def test_intent_looks_a_photo_up_before_it_edits_the_last_picture() -> None:
    """After a picture, "send me a photo of X" still wants a real photo, not an edit."""
    text = "send me a photo of the eiffel tower"
    rows = _rows(AFTER_PICTURE)
    edit = image_gen_request(text, rows)
    assert edit is not None and edit.revision  # the edit reading alone would draw it
    verdict = _verdict(text, AFTER_PICTURE)
    assert verdict["lookup_query"] == "eiffel tower"
    assert verdict["generate_prompt"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "x" * 2001},
        {"text": "draw a cat", "chat_id": "not-a-uuid"},
    ],
)
def test_intent_refuses_a_malformed_request(payload: dict[str, Any]) -> None:
    with _client(_user()) as (client, _get_chat, _recent):
        response = client.post(
            "/images/intent", headers={"Authorization": "Bearer tok"}, json=payload
        )
    assert response.status_code == 422
