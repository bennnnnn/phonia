"""Speech, scan reads, pictures and memory edits wait for consent to outside AI services.

Each answers 403 ``{"detail": {"code": "consent_required", …}}`` before it reads
the request, so nothing reaches a provider; the phone opens its consent screen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import get_db
from app.core.deps import get_current_user, get_settings_dep
from app.main import create_app

pytestmark = pytest.mark.usefixtures("consent_enforced")

_AGREED = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
_ROUTES = [
    ("post", "/speech/transcribe", {"audio_base64": "AAAA", "filename": "a.m4a"}),
    ("post", "/speech/tts", {"text": "hello"}),
    ("post", "/speech/live/session", {}),
    ("post", "/speech/live/tool", {"call_id": "call-123456", "name": "web_search"}),
    ("post", "/math/scan/read", None),
    ("post", "/physics/scan/read", None),
    ("post", "/chemistry/scan/read", None),
    ("post", "/images/generate", {"chat_id": str(uuid4()), "prompt": "a lighthouse at dusk"}),
    ("post", "/images/intent", {"text": "draw a lighthouse at dusk"}),
    ("post", "/memories/instruct", {"instruction": "remember that I prefer metric units"}),
]


def _client(
    user: Any, *, stored_consent: datetime | None = None, settings: Settings | None = None
) -> TestClient:
    """The app with ``user`` signed in; the row read on a refusal holds ``stored_consent``."""

    async def refresh(row: Any, attribute_names: list[str] | None = None) -> None:
        row.ai_data_consent_at = stored_consent

    session = SimpleNamespace(refresh=AsyncMock(side_effect=refresh), commit=AsyncMock())

    async def db() -> Any:
        yield session

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_settings_dep] = lambda: settings or Settings()
    return TestClient(app)


def _send(client: TestClient, method: str, path: str, body: Any) -> Any:
    with patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)):
        return client.request(
            method, path, headers={"Authorization": "Bearer tok"}, json=body or {}
        )


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES, ids=[r[1] for r in _ROUTES])
def test_a_request_without_consent_is_refused(method: str, path: str, body: Any) -> None:
    user = SimpleNamespace(id=uuid4(), ai_data_consent_at=None)
    response = _send(_client(user), method, path, body)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "consent_required"


@pytest.mark.parametrize(
    ("path", "off"),
    [
        ("/speech/transcribe", {"speech_transcription_enabled": False}),
        ("/math/scan/read", {"math_tools_enabled": False}),
    ],
)
def test_consent_given_on_another_machine_lets_the_request_through(
    path: str, off: dict[str, Any]
) -> None:
    """The cached user trailed the agreement; the row read before refusing has it.

    The feature is off, so getting past the gate answers 404, not 403.
    """
    user = SimpleNamespace(id=uuid4(), ai_data_consent_at=None)
    client = _client(user, stored_consent=_AGREED, settings=Settings.model_validate(off))
    response = _send(client, "post", path, {"audio_base64": "AAAA", "filename": "a.m4a"})

    assert response.status_code == 404
    assert user.ai_data_consent_at == _AGREED


@pytest.mark.asyncio
async def test_an_account_that_agreed_is_not_read_again() -> None:
    from app.core.consent import get_consented_user

    user = SimpleNamespace(id=uuid4(), ai_data_consent_at=_AGREED)
    session = SimpleNamespace(refresh=AsyncMock())
    assert await get_consented_user(user=user, session=session) is user  # type: ignore[arg-type]
    session.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_withdrawal_on_another_machine_is_honoured_at_once(fake_redis) -> None:
    """The cached row said yes for up to a minute after a withdrawal elsewhere.

    A copy is served only under the account's current generation (``core/user_cache``),
    and the withdrawal's publish replaced it, so the gate gets the row read again.
    """
    from app.core import user_cache
    from app.core.cache_generation import bump_generation

    user = SimpleNamespace(id=uuid4(), ai_data_consent_at=_AGREED)
    user_cache.remember_user(user, "loaded-before")  # type: ignore[arg-type]
    key = user_cache.generation_key(user.id)
    await bump_generation(fake_redis, key)  # another machine's PATCH /auth/me
    current = await fake_redis.get(key)

    assert user_cache.cached_user(user.id, current) is None


@pytest.mark.asyncio
async def test_the_re_read_ends_its_transaction_before_the_route_runs() -> None:
    """A stream after the gate must not hold the re-read's connection idle in transaction."""
    from app.core.consent import get_consented_user

    calls: list[str] = []

    async def refresh(row: Any, attribute_names: list[str] | None = None) -> None:
        calls.append("refresh")
        row.ai_data_consent_at = _AGREED

    async def commit() -> None:
        calls.append("commit")

    user = SimpleNamespace(id=uuid4(), ai_data_consent_at=None)
    session = SimpleNamespace(refresh=refresh, commit=commit)
    assert await get_consented_user(user=user, session=session) is user  # type: ignore[arg-type]
    assert calls == ["refresh", "commit"]
