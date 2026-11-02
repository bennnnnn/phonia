"""Tests for JWT refresh/logout token service."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import jwt
import pytest

from app.core.access_tokens import create_access_token
from app.core.config import Settings
from app.exceptions import AuthenticationError
from app.modules.account import tokens as tokens_service


@pytest.mark.asyncio
async def test_issue_and_refresh_token_pair(fake_redis):
    settings = Settings(jwt_secret="x" * 32)
    from app.tests.api_support import api_user

    user = api_user()
    session = AsyncMock()
    access, refresh = await tokens_service.issue_token_pair(fake_redis, user.id, settings)

    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)):
        new_access, new_refresh, user_out = await tokens_service.refresh_token_pair(
            fake_redis, refresh, session, settings
        )

    assert new_access != access
    assert new_refresh != refresh
    assert user_out.id == user.id


@pytest.mark.asyncio
async def test_refresh_rejects_unknown_token(fake_redis):
    settings = Settings(jwt_secret="x" * 32)
    session = AsyncMock()

    with pytest.raises(AuthenticationError):
        await tokens_service.refresh_token_pair(
            fake_redis, "not-a-real-refresh-token", session, settings
        )


@pytest.mark.asyncio
async def test_revoke_access_token_blocks_verify(fake_redis):
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    token = create_access_token(user_id, settings)
    await tokens_service.verify_access_token(fake_redis, token, settings)

    await tokens_service.revoke_access_token(fake_redis, token, settings)
    with pytest.raises(AuthenticationError, match="revoked"):
        await tokens_service.verify_access_token(fake_redis, token, settings)


@pytest.mark.asyncio
async def test_revoke_refresh_token(fake_redis):
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    _access, refresh = await tokens_service.issue_token_pair(fake_redis, user_id, settings)
    await tokens_service.revoke_refresh_token(fake_redis, refresh)
    assert await fake_redis.get(f"refresh:{refresh}") is None


@pytest.mark.asyncio
async def test_reused_refresh_token_revokes_every_session(fake_redis):
    """Presenting an already-rotated-out refresh token is a compromise
    signal: it must kill every refresh token for that user, not just fail
    the one request."""
    settings = Settings(jwt_secret="x" * 32)
    from app.tests.api_support import api_user

    user = api_user()
    session = AsyncMock()

    _access1, refresh1 = await tokens_service.issue_token_pair(fake_redis, user.id, settings)

    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)):
        # Legitimate rotation: refresh1 -> refresh2.
        _access2, refresh2, _ = await tokens_service.refresh_token_pair(
            fake_redis, refresh1, session, settings
        )
        assert await fake_redis.get(f"refresh:{refresh2}") is not None

        # Attacker (or a delayed retry) replays the now-superseded refresh1.
        with pytest.raises(AuthenticationError):
            await tokens_service.refresh_token_pair(fake_redis, refresh1, session, settings)

    # The legitimate device's rotated-to token is dead too — the whole
    # session was killed, not just the stolen token.
    assert await fake_redis.get(f"refresh:{refresh2}") is None
    revoked_since = await fake_redis.get(f"revoked_since:{user.id}")
    assert revoked_since is not None


@pytest.mark.asyncio
async def test_revoked_since_blocks_existing_access_tokens(fake_redis):
    """An access token issued before a detected-reuse event must stop
    verifying, even though it hasn't naturally expired yet."""
    settings = Settings(jwt_secret="x" * 32)
    from app.tests.api_support import api_user

    user = api_user()
    session = AsyncMock()

    access_before_reuse = create_access_token(user.id, settings)
    await tokens_service.verify_access_token(fake_redis, access_before_reuse, settings)

    _access1, refresh1 = await tokens_service.issue_token_pair(fake_redis, user.id, settings)
    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)):
        _access2, _refresh2, _ = await tokens_service.refresh_token_pair(
            fake_redis, refresh1, session, settings
        )
        with pytest.raises(AuthenticationError):
            await tokens_service.refresh_token_pair(fake_redis, refresh1, session, settings)

    with pytest.raises(AuthenticationError, match="revoked"):
        await tokens_service.verify_access_token(fake_redis, access_before_reuse, settings)


@pytest.mark.asyncio
async def test_first_time_unknown_refresh_token_does_not_trigger_revocation(fake_redis):
    """A token that was never issued (typo, bogus value) has no tombstone —
    it must just fail, not be treated as a reuse/compromise signal."""
    settings = Settings(jwt_secret="x" * 32)
    session = AsyncMock()

    with pytest.raises(AuthenticationError):
        await tokens_service.refresh_token_pair(fake_redis, "never-issued-token", session, settings)

    # No user to revoke since the token was never associated with one — the
    # important behavior is simply that this doesn't crash and stays a plain
    # "invalid token" failure.


@pytest.mark.asyncio
async def test_logout_removes_token_from_user_session_set(fake_redis):
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    _access, refresh = await tokens_service.issue_token_pair(fake_redis, user_id, settings)

    await tokens_service.revoke_refresh_token(fake_redis, refresh)

    assert not await fake_redis.sismember(f"refresh_user:{user_id}", refresh)


@pytest.mark.asyncio
async def test_logout_without_refresh_ends_only_this_devices_session(fake_redis):
    """A phone that could not read its refresh token signs out itself, not every device."""
    from unittest.mock import AsyncMock, MagicMock

    from app.models.schemas import LogoutRequest
    from app.modules.account import api as auth_router

    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    access, refresh_here = await tokens_service.issue_token_pair(fake_redis, user_id, settings)
    other_access, refresh_other = await tokens_service.issue_token_pair(
        fake_redis, user_id, settings
    )

    request = MagicMock()
    request.headers = {"authorization": f"Bearer {access}"}
    await auth_router.logout(
        LogoutRequest(refresh_token=None),
        request=request,
        settings=settings,
        redis=fake_redis,
        session=AsyncMock(),
    )

    # This session is over: its refresh token and its access token.
    assert await fake_redis.get(f"refresh:{refresh_here}") is None
    with pytest.raises(AuthenticationError):
        await tokens_service.verify_access_token(fake_redis, access, settings)
    # The other device stays signed in.
    assert await fake_redis.get(f"refresh:{refresh_other}") is not None
    assert await fake_redis.smembers(f"refresh_user:{user_id}") == {refresh_other}
    assert await tokens_service.verify_access_token(fake_redis, other_access, settings) == user_id


@pytest.mark.asyncio
async def test_purge_user_sessions_kills_all_refresh_tokens(fake_redis):
    """Account deletion must revoke every outstanding session, not just rely
    on the DB user check to stop a logged-in client."""
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    _a1, refresh1 = await tokens_service.issue_token_pair(fake_redis, user_id, settings)
    _a2, refresh2 = await tokens_service.issue_token_pair(fake_redis, user_id, settings)

    await tokens_service.purge_user_sessions(fake_redis, user_id, settings)

    assert await fake_redis.get(f"refresh:{refresh1}") is None
    assert await fake_redis.get(f"refresh:{refresh2}") is None
    assert await fake_redis.smembers(f"refresh_user:{user_id}") == set()
    # Any access token issued before now is treated as revoked.
    assert await fake_redis.get(f"revoked_since:{user_id}") is not None


@pytest.mark.asyncio
async def test_purge_user_sessions_raises_on_redis_failure(fake_redis):
    """M1: Redis outage during account delete must fail (503), not silently
    succeed — otherwise live sessions can call the API until JWT expiry."""
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    with (
        patch(
            "redis.asyncio.client.Pipeline.smembers",
            AsyncMock(side_effect=RuntimeError("redis down")),
        ),
        pytest.raises(RuntimeError, match="redis down"),
    ):
        await tokens_service.purge_user_sessions(fake_redis, user_id, settings)


@pytest.mark.asyncio
async def test_sign_in_drops_sessions_whose_refresh_token_expired(fake_redis):
    """refresh_user:<id> kept every refresh token a user ever signed in with.

    A token that simply expires (a device not opened for 30 days, a
    reinstall) left its member behind, and each sign-in renewed the set's TTL,
    so for an active user the set only grew.
    """
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    _a1, expired = await tokens_service.issue_token_pair(fake_redis, user_id, settings)
    _a2, live = await tokens_service.issue_token_pair(fake_redis, user_id, settings)
    await fake_redis.delete(f"refresh:{expired}")  # its own TTL ran out

    _a3, newest = await tokens_service.issue_token_pair(fake_redis, user_id, settings)

    assert await fake_redis.smembers(f"refresh_user:{user_id}") == {live, newest}
    sessions = await tokens_service.list_sessions(fake_redis, user_id, current_session_id=None)
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_issue_stores_a_json_session_that_refreshes(fake_redis):
    settings = Settings(jwt_secret="x" * 32)
    from app.tests.api_support import api_user

    user = api_user()
    session = AsyncMock()
    access, refresh = await tokens_service.issue_token_pair(
        fake_redis, user.id, settings, device_label="Pixel 8", platform="android"
    )
    record = tokens_service.parse_refresh_record(await fake_redis.get(f"refresh:{refresh}"))
    assert record is not None
    assert record["user_id"] == str(user.id)
    assert record["device_label"] == "Pixel 8"
    payload = jwt.decode(access, settings.jwt_secret, algorithms=["HS256"])
    assert payload.get("sid") == record["session_id"]

    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)):
        new_access, new_refresh, user_out = await tokens_service.refresh_token_pair(
            fake_redis, refresh, session, settings, device_label="iPhone"
        )
    assert user_out.id == user.id
    assert new_access != access
    rotated = tokens_service.parse_refresh_record(await fake_redis.get(f"refresh:{new_refresh}"))
    assert rotated is not None
    assert rotated["device_label"] == "iPhone"
    assert rotated["session_id"] == record["session_id"]


@pytest.mark.parametrize(
    "stored",
    [
        "plain-user-id",
        '{"user_id": "00000000-0000-0000-0000-000000000001"}',
        '{"user_id": "not-a-uuid", "session_id": "s1"}',
        "[1, 2]",
    ],
)
def test_a_record_this_release_never_writes_is_refused(stored: str) -> None:
    assert tokens_service.parse_refresh_record(stored) is None


@pytest.mark.asyncio
async def test_refreshing_an_unreadable_record_signs_that_device_out(fake_redis):
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    await fake_redis.set("refresh:old", str(user_id))
    await fake_redis.sadd(f"refresh_user:{user_id}", "old")

    with pytest.raises(AuthenticationError):
        await tokens_service.refresh_token_pair(fake_redis, "old", AsyncMock(), settings)

    assert await fake_redis.exists("refresh:old") == 0
    assert await tokens_service.refresh_token_user(fake_redis, "old") is None
    assert await tokens_service.list_sessions(fake_redis, user_id, current_session_id=None) == []


@pytest.mark.asyncio
async def test_list_and_revoke_sessions(fake_redis):
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    access, _refresh = await tokens_service.issue_token_pair(
        fake_redis, user_id, settings, device_label="iPad"
    )
    await tokens_service.issue_token_pair(fake_redis, user_id, settings, device_label="Mac")
    current = tokens_service.session_id_from_access_token(access, settings)
    sessions = await tokens_service.list_sessions(fake_redis, user_id, current_session_id=current)
    assert len(sessions) == 2
    current_row = next(row for row in sessions if row["current"])
    other = next(row for row in sessions if not row["current"])
    assert current_row["device_label"] == "iPad"

    with pytest.raises(tokens_service.CurrentSessionError):
        await tokens_service.revoke_session(
            fake_redis, user_id, current_row["id"], current_session_id=current, settings=settings
        )
    await tokens_service.revoke_session(
        fake_redis, user_id, other["id"], current_session_id=current, settings=settings
    )
    remaining = await tokens_service.list_sessions(fake_redis, user_id, current_session_id=current)
    assert len(remaining) == 1
    assert remaining[0]["current"] is True


@pytest.mark.asyncio
async def test_revoke_session_signs_that_device_out_now(fake_redis):
    """Removing a device must stop its access token too, not only its refresh token."""
    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    mine, _ = await tokens_service.issue_token_pair(fake_redis, user_id, settings)
    lost_phone, _ = await tokens_service.issue_token_pair(fake_redis, user_id, settings)
    current = tokens_service.session_id_from_access_token(mine, settings)
    lost = tokens_service.session_id_from_access_token(lost_phone, settings)
    assert lost is not None

    await tokens_service.revoke_session(
        fake_redis, user_id, lost, current_session_id=current, settings=settings
    )

    with pytest.raises(AuthenticationError):
        await tokens_service.verify_access_token(fake_redis, lost_phone, settings)
    assert await tokens_service.verify_access_token(fake_redis, mine, settings) == user_id
    ttl = await fake_redis.ttl(f"revoked:sid:{lost}")
    assert 0 < ttl <= settings.jwt_expire_minutes * 60
