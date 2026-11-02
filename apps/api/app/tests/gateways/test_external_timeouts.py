"""Outbound calls the request path waits on have short, bounded timeouts.

* R2 (boto3) used botocore defaults: 60s connect, 60s read, legacy retries
  (5 attempts). Each call holds one of the default executor's threads (5 on
  a 1-CPU Fly machine), which Google sign-in and PDF extraction share.
* Google sign-in fetched certs with google-auth's default 120s timeout, and
  a failed fetch (``TransportError``) surfaced as a 500.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.gateways import google_auth
from app.gateways.storage_gateway import R2StorageGateway


def _r2_settings(**overrides: Any) -> Settings:
    return Settings(
        r2_account_id="acct",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        r2_bucket="bucket",
        **overrides,
    )


@pytest.mark.parametrize(
    "overrides, connect, read, attempts",
    [
        ({}, 5.0, 20.0, 3),
        (
            {
                "r2_connect_timeout_seconds": 2.0,
                "r2_read_timeout_seconds": 9.0,
                "r2_max_attempts": 2,
            },
            2.0,
            9.0,
            2,
        ),
    ],
)
def test_r2_client_has_bounded_timeouts_and_retries(
    overrides: dict[str, Any], connect: float, read: float, attempts: int
) -> None:
    gateway = R2StorageGateway(_r2_settings(**overrides))
    config = gateway._client.meta.config
    assert config.connect_timeout == connect
    assert config.read_timeout == read
    assert config.retries == {"total_max_attempts": attempts, "mode": "standard"}


class _RecordingSession:
    """A ``requests.Session`` stand-in: records the timeout, then fails or stalls."""

    def __init__(self, *, status: int = 500, delay: float = 0.0) -> None:
        self.timeouts: list[object] = []
        self._status = status
        self._delay = delay

    def close(self) -> None:
        """``google.auth``'s ``Request`` closes its session when it is collected."""

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.timeouts.append(kwargs.get("timeout"))
        if self._delay:
            time.sleep(self._delay)

        class _Response:
            status_code = self._status
            headers: dict[str, str] = {}
            content = b"{}"

        return _Response()


@pytest.fixture
def google_session():
    from google.auth.transport import requests as g_requests

    sessions: list[_RecordingSession] = []

    def install(session: _RecordingSession) -> None:
        sessions.append(session)
        google_auth._google_request = g_requests.Request(session=session)  # type: ignore[arg-type]

    previous = google_auth._google_request
    yield install
    google_auth._google_request = previous


@pytest.mark.parametrize("configured, expected", [(None, 10.0), (3.0, 3.0)])
async def test_google_cert_fetch_uses_a_short_timeout(
    google_session: Any, configured: float | None, expected: float
) -> None:
    session = _RecordingSession(status=500)
    google_session(session)
    settings = (
        Settings(google_client_id="cid")
        if configured is None
        else Settings(google_client_id="cid", google_auth_timeout_seconds=configured)
    )
    with pytest.raises(google_auth.GoogleAuthUnavailableError):
        await google_auth.verify_google_id_token("a.b.c", settings)
    assert session.timeouts == [expected]


@pytest.mark.wall_clock
async def test_google_verify_gives_up_when_the_fetch_thread_stalls(google_session: Any) -> None:
    google_session(_RecordingSession(status=200, delay=1.5))
    settings = Settings(google_client_id="cid", google_auth_timeout_seconds=0.2)
    started = time.monotonic()
    with (
        patch.object(google_auth, "_THREAD_GRACE_SECONDS", 0.1),
        pytest.raises(google_auth.GoogleAuthUnavailableError),
    ):
        await google_auth.verify_google_id_token("a.b.c", settings)
    assert time.monotonic() - started < 1.0
    await asyncio.sleep(1.5)  # let the stalled thread finish before teardown


@pytest.mark.parametrize(
    "error, expected_status",
    [
        (google_auth.GoogleAuthError("Invalid Google ID token"), 401),
        ("unavailable", 503),
    ],
)
async def test_google_sign_in_maps_provider_outage_to_503(
    error: object, expected_status: int
) -> None:
    import fakeredis.aioredis

    from app.main import create_app

    raised = (
        google_auth.GoogleAuthUnavailableError("Google sign-in is unavailable")
        if error == "unavailable"
        else error
    )

    async def fail(*_args: object, **_kwargs: object) -> None:
        raise raised  # type: ignore[misc]

    from app.core.deps import get_redis

    app = create_app()
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: redis
    with patch("app.modules.account.service.verify_google_id_token", fail):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            response = await client.post("/auth/google", json={"id_token": "x" * 40})
    assert response.status_code == expected_status
    if expected_status == 503:
        assert response.headers.get("retry-after")
