"""Every refusal a service raises answers with one body (code-health audit DUP-10).

A dummy route raises each ``DomainError`` subclass: the app's handler answers its status
with ``{"detail": {"code", "message", ...}}``, and nothing internal (a user id) leaks.
"""

from __future__ import annotations

import importlib
import pkgutil
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app as app_package
from app.core.consent import ConsentRefusedError
from app.core.domain_errors import register_domain_error_handler
from app.exceptions import DomainError, RateLimitedError
from app.modules.account.email_authority import AccountExistsError
from app.modules.account.settings_proposal import SettingsProposalError
from app.modules.account.signin_refusals import SignInRefusedError
from app.modules.attachments.upload import AttachmentUploadError
from app.modules.attachments.workflow import AttachmentWorkflowError
from app.modules.billing.subscription import StoreUnreachableError
from app.modules.chat.service import ChatsError
from app.modules.images.generation import ImageGenerationError
from app.modules.images.search import ImageSearchError
from app.modules.memory.crud import MemoryEmptyTextError
from app.modules.memory.instruct import MemoryInstructionFailedError, MemoryOffError
from app.modules.memory.locks import MemoryWriteLockBusyError
from app.modules.speech.gates import SpeechRefusedError
from app.modules.todos.crud import TodosError
from app.modules.todos.proposals import ProposalError
from app.repositories.keyset import InvalidCursorError
from app.services.scan_read import ScanRefusedError

# (refusal, status, code) for every subclass.
CASES: list[tuple[DomainError, int, str]] = [
    (ChatsError("Chat not found", status_code=404), 404, "not_found"),
    (TodosError("recurrence_rule requires due_at", status_code=422), 422, "invalid"),
    (ProposalError("This expired. Ask again.", status_code=410), 410, "expired"),
    (SettingsProposalError("That's already set."), 400, "invalid"),
    (ImageGenerationError("Not available", status_code=404, code="not_available"), 404, "not_available"),
    (ImageSearchError("Could not link reference photo", status_code=500), 500, "failed"),
    (AttachmentUploadError("Unsupported content type", status_code=400, code="unsupported_type"), 400, "unsupported_type"),
    (AttachmentWorkflowError("File missing", status_code=404), 404, "not_found"),
    (MemoryWriteLockBusyError(uuid4()), 409, "memory_busy"),
    (MemoryEmptyTextError(), 400, "memory_empty"),
    (MemoryOffError(), 409, "memory_off"),
    (MemoryInstructionFailedError(), 502, "memory_edit_failed"),
    (SpeechRefusedError("Too many requests", status_code=429), 429, "rate_limited"),
    (ScanRefusedError("Image too large", status_code=413, code="image_too_large"), 413, "image_too_large"),
    (ConsentRefusedError(), 403, "consent_required"),
    (AccountExistsError("apple"), 409, "account_exists"),
    (SignInRefusedError("Invalid Google ID token", code="google_token_invalid"), 401, "google_token_invalid"),
    (SignInRefusedError("Sign-in failed"), 401, "sign_in_failed"),
    (InvalidCursorError(), 422, "invalid_cursor"),
    (StoreUnreachableError("The store did not answer"), 503, "store_unreachable"),
    (RateLimitedError("Too many chat requests.", retry_after_seconds=60), 429, "rate_limited"),
]  # fmt: skip


def _client(refusal: DomainError) -> TestClient:
    app = FastAPI()
    register_domain_error_handler(app)

    @app.get("/refuse")
    async def refuse() -> None:
        raise refusal

    return TestClient(app)


@pytest.mark.parametrize(("refusal", "status", "code"), CASES)
def test_each_refusal_answers_its_status_and_code(
    refusal: DomainError, status: int, code: str
) -> None:
    response = _client(refusal).get("/refuse")

    assert response.status_code == status
    detail = response.json()["detail"]
    assert detail["code"] == code
    assert detail["message"] == refusal.message
    assert "user_id" not in detail


def test_a_refusal_carries_its_fields_and_headers() -> None:
    refused = DomainError("Slow down", status_code=429, headers={"Retry-After": "5"}, limit=3)
    response = _client(refused).get("/refuse")

    assert response.headers["Retry-After"] == "5"
    assert response.json() == {
        "detail": {"code": "rate_limited", "message": "Slow down", "limit": 3}
    }
    assert _client(AccountExistsError("google")).get("/refuse").json()["detail"][
        "sign_in_with"
    ] == ("google")


def test_a_rate_limit_says_its_wait() -> None:
    response = _client(RateLimitedError("Slow down", retry_after_seconds=60)).get("/refuse")
    assert response.headers["Retry-After"] == "60"


def _subclasses(cls: type[DomainError]) -> set[type[DomainError]]:
    found: set[type[DomainError]] = set()
    for sub in cls.__subclasses__():
        found |= {sub, *_subclasses(sub)}
    return found


def test_every_refusal_class_is_covered() -> None:
    for module in pkgutil.walk_packages(app_package.__path__, "app."):
        if ".tests" not in module.name and module.name != "app.worker_main":
            importlib.import_module(module.name)
    covered = {type(refusal) for refusal, _status, _code in CASES}
    missing = sorted(cls.__qualname__ for cls in _subclasses(DomainError) - covered)
    assert not missing, f"Add a case for each refusal class: {missing}"
