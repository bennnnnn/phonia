"""Memory documents, document delete and direct edits over HTTP."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import get_db
from app.core.deps import get_current_user, get_settings_dep
from app.core.domain_errors import register_domain_error_handler
from app.models.orm import Memory
from app.modules.memory import crud, locks
from app.modules.memory import instruct as instruct_service
from app.modules.memory.api import router
from app.modules.memory.documents import MemoryDocument
from app.modules.memory.instruct import MemoryInstructionOutcome


def _client() -> tuple[TestClient, SimpleNamespace]:
    app = FastAPI()
    app.include_router(router)
    register_domain_error_handler(app)
    user = SimpleNamespace(id=uuid4(), memory_enabled=True, memory_history_scanned_at=None)
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    return TestClient(app), user


def _document() -> MemoryDocument:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    fact = Memory(
        id=uuid4(),
        user_id=uuid4(),
        type="preference",
        topic="preferences",
        text="User prefers short answers",
        confidence=0.9,
        status="active",
        sensitivity="normal",
        importance=0.7,
        last_confirmed_at=now,
        created_at=now,
        updated_at=now,
    )
    return MemoryDocument(
        key="preferences",
        group="you",
        title="Preferences",
        summary="How you want Recall to respond",
        updated_at=now,
        facts=[fact],
    )


def test_documents_answer_an_unchanged_read_with_304():
    """A repeat visit to Memory sends back the ETag; unchanged pages cost no body."""
    client, _ = _client()
    document = _document()
    with (
        patch(
            "app.modules.memory.api.documents_service.list_documents",
            AsyncMock(return_value=[document]),
        ),
        patch(
            "app.modules.memory.api.history_scan.request_history_scan",
            AsyncMock(return_value=False),
        ),
        patch("app.modules.memory.api.get_redis_client"),
    ):
        first = client.get("/memories/documents")
        etag = first.headers["etag"]
        again = client.get("/memories/documents", headers={"If-None-Match": etag})
        document.facts[0].text = "User prefers long answers"
        changed = client.get("/memories/documents", headers={"If-None-Match": etag})

    assert first.status_code == 200
    assert etag.startswith('W/"')
    # Never kept by a shared cache: the pages are one person's memory.
    assert first.headers["cache-control"] == "private, no-cache"
    assert again.status_code == 304
    assert again.content == b""
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag


def test_documents_endpoint_lists_documents_and_starts_the_history_scan():
    client, user = _client()
    with (
        patch(
            "app.modules.memory.api.documents_service.list_documents",
            AsyncMock(return_value=[_document()]),
        ),
        patch(
            "app.modules.memory.api.history_scan.request_history_scan",
            AsyncMock(return_value=True),
        ) as request_scan,
        patch("app.modules.memory.api.get_redis_client"),
    ):
        response = client.get("/memories/documents")

    assert response.status_code == 200
    body = response.json()
    assert body["scanning"] is True
    [document] = body["documents"]
    assert document["key"] == "preferences"
    assert document["group"] == "you"
    assert document["facts"][0]["text"] == "User prefers short answers"
    assert document["facts"][0]["topic"] == "preferences"
    assert request_scan.await_args.args[1] is user


def test_document_facts_say_where_they_were_learned_and_if_muted():
    """M11/M12: each fact carries its status and the chat it came from."""
    client, _user = _client()
    document = _document()
    chat_id = uuid4()
    document.facts[0].source_chat_id = chat_id
    document.facts[0].status = "muted"
    with (
        patch(
            "app.modules.memory.api.documents_service.list_documents",
            AsyncMock(return_value=[document]),
        ),
        patch(
            "app.modules.memory.api.enqueue_policy.source_chat_titles",
            AsyncMock(return_value={chat_id: "Planning the Lalibela trip"}),
        ),
        patch(
            "app.modules.memory.api.history_scan.request_history_scan",
            AsyncMock(return_value=False),
        ),
        patch("app.modules.memory.api.get_redis_client"),
    ):
        response = client.get("/memories/documents")

    [fact] = response.json()["documents"][0]["facts"]
    assert fact["status"] == "muted"
    assert fact["source_chat_title"] == "Planning the Lalibela trip"


@pytest.mark.parametrize(
    "topic,result,status",
    [
        ("area:recall", True, 204),
        ("tech-stack", False, 404),
        ("not-a-topic", None, 404),
    ],
)
def test_delete_document(topic, result, status):
    client, user = _client()
    with patch.object(crud, "delete_memory_document", AsyncMock(return_value=result)) as delete:
        response = client.delete(f"/memories/documents/{topic}")

    assert response.status_code == status
    if result is None:
        delete.assert_not_awaited()
    else:
        assert delete.await_args.args[1:] == (user.id, topic)


def test_delete_document_while_memory_is_busy_is_a_conflict():
    client, _ = _client()
    with patch.object(
        crud,
        "delete_memory_document",
        AsyncMock(side_effect=locks.MemoryWriteLockBusyError(uuid4())),
    ):
        response = client.delete("/memories/documents/profile")
    assert response.status_code == 409


def _instruct_patches(*, spend_capped=False, allowed=True, outcome=None, error=None):
    apply = AsyncMock(return_value=outcome, side_effect=error)
    return (
        patch("app.modules.memory.api.get_redis_client"),
        patch(
            "app.modules.memory.api.quota_service.global_spend_exceeded",
            AsyncMock(return_value=spend_capped),
        ),
        patch(
            "app.modules.memory.api.allow_request_unless_down",
            AsyncMock(return_value=allowed),
        ),
        patch("app.modules.memory.api.instruct_service.apply_memory_instruction", apply),
        patch(
            "app.modules.memory.api.documents_service.list_documents",
            AsyncMock(return_value=[_document()]),
        ),
    )


def test_instruct_applies_the_edit_and_returns_the_documents():
    client, user = _client()
    patches = _instruct_patches(
        outcome=MemoryInstructionOutcome(applied=1, reply="Saved: keep lists short.")
    )
    with patches[0], patches[1], patches[2], patches[3] as apply, patches[4]:
        response = client.post(
            "/memories/instruct",
            json={"instruction": "  Keep lists under five things ", "topic": "preferences"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Saved: keep lists short."
    assert body["applied"] == 1
    assert body["documents"][0]["key"] == "preferences"
    assert apply.await_args.kwargs == {
        "user_id": user.id,
        "instruction": "Keep lists under five things",
        "focus_topic": "preferences",
    }


@pytest.mark.parametrize(
    "kwargs,status,code",
    [
        # Paused by the spend cap is no outage: "unavailable" is Redis or the database down.
        ({"spend_capped": True}, 503, "memory_spend_cap"),
        ({"allowed": False}, 429, "rate_limited"),
        ({"error": locks.MemoryWriteLockBusyError(uuid4())}, 409, "memory_busy"),
        ({"error": instruct_service.MemoryOffError()}, 409, "memory_off"),
        ({"error": instruct_service.MemoryInstructionFailedError()}, 502, "memory_edit_failed"),
    ],
)
def test_instruct_errors(kwargs, status, code):
    """Each refusal names itself: the phone tells busy, off and too many apart (CLAR-08)."""
    client, _ = _client()
    patches = _instruct_patches(**kwargs)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        response = client.post("/memories/instruct", json={"instruction": "Remember I like tea"})
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


@pytest.mark.parametrize("instruction", ["", "x" * 501])
def test_instruct_rejects_empty_or_long_instructions(instruction):
    client, _ = _client()
    response = client.post("/memories/instruct", json={"instruction": instruction})
    assert response.status_code == 422
