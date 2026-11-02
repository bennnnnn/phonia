"""Refresh must survive transient failures and respect concurrent logout."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from app.core.access_tokens import redis_str
from app.core.config import Settings
from app.exceptions import AuthenticationError, RedisUnavailableError
from app.modules.account import tokens as tokens
from app.tests.api_support import api_user


def _refresh_user_id(raw: str | bytes, refresh: str) -> str:
    record = tokens.parse_refresh_record(raw)
    assert record is not None
    return str(record["user_id"])


@pytest.mark.asyncio
async def test_refresh_database_failure_preserves_credential_for_retry(fake_redis):
    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, settings)
    failure = OperationalError("SELECT user", {}, RuntimeError("database unavailable"))
    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(side_effect=failure)):
        with pytest.raises(OperationalError):
            await tokens.refresh_token_pair(fake_redis, refresh, AsyncMock(), settings)

    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)):
        access, replacement, _ = await tokens.refresh_token_pair(
            fake_redis, refresh, AsyncMock(), settings
        )
    assert replacement != refresh
    assert await tokens.verify_access_token(fake_redis, access, settings) == user.id


@pytest.mark.asyncio
@pytest.mark.parametrize("purge", [False, True], ids=["logout", "account-purge"])
async def test_refresh_cannot_restore_session_after_logout_during_database_read(fake_redis, purge):
    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, settings)
    lookup_started = asyncio.Event()
    lookup_resume = asyncio.Event()

    async def lookup(*_args):
        lookup_started.set()
        await lookup_resume.wait()
        return user

    with patch("app.modules.account.tokens.users_repo.get_by_id", side_effect=lookup):
        task = asyncio.create_task(
            tokens.refresh_token_pair(fake_redis, refresh, AsyncMock(), settings)
        )
        try:
            await asyncio.wait_for(lookup_started.wait(), timeout=2)
            if purge:
                await tokens.purge_user_sessions(fake_redis, user.id, settings)
            else:
                await tokens.revoke_refresh_token(fake_redis, refresh)
        finally:
            lookup_resume.set()
        with pytest.raises(AuthenticationError, match="Invalid refresh token"):
            await task

    assert await fake_redis.smembers(f"refresh_user:{user.id}") == set()


@pytest.mark.asyncio
async def test_sign_in_immediately_after_purge_issues_valid_access_token(fake_redis):
    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    now = datetime.now(UTC).replace(microsecond=100_000)
    later_same_second = now.replace(microsecond=200_000)
    with patch("app.modules.account.tokens.datetime") as clock:
        clock.now.return_value = now
        await tokens.purge_user_sessions(fake_redis, user.id, settings)
    with patch("app.core.access_tokens.datetime") as clock:
        clock.now.return_value = later_same_second
        access, _ = await tokens.issue_token_pair(fake_redis, user.id, settings)
    assert await tokens.verify_access_token(fake_redis, access, settings) == user.id


@pytest.mark.asyncio
async def test_refresh_redis_failure_before_commit_preserves_credential(fake_redis):
    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, settings)
    with (
        patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)),
        patch(
            "redis.asyncio.client.Pipeline.execute",
            AsyncMock(side_effect=RedisConnectionError("temporarily unavailable")),
        ),
    ):
        with pytest.raises(RedisUnavailableError):
            await tokens.refresh_token_pair(fake_redis, refresh, AsyncMock(), settings)

    raw = await fake_redis.get(f"refresh:{refresh}")
    assert isinstance(raw, bytes | str)
    assert _refresh_user_id(raw, refresh) == str(user.id)
    assert await fake_redis.get(f"refresh_used:{refresh}") is None


@pytest.mark.asyncio
async def test_refresh_lost_watch_connection_keeps_session_retryable(fake_redis):
    from redis.exceptions import WatchError

    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, settings)
    with (
        patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)),
        patch(
            "redis.asyncio.client.Pipeline.execute",
            AsyncMock(side_effect=WatchError("connection lost while watching")),
        ),
        pytest.raises(RedisUnavailableError),
    ):
        await tokens.refresh_token_pair(fake_redis, refresh, AsyncMock(), settings)
    raw = await fake_redis.get(f"refresh:{refresh}")
    assert isinstance(raw, bytes | str)
    assert _refresh_user_id(raw, refresh) == str(user.id)


async def _live_sessions(redis, user_id) -> set[str]:
    return {redis_str(token) for token in await redis.smembers(f"refresh_user:{user_id}")}


@pytest.mark.asyncio
async def test_concurrent_refreshes_of_one_token_share_one_session(fake_redis):
    """Two refreshes of one token in flight at once both succeed, with one successor.

    One used to win and the other revoked every session of the account, the winner's
    included: the phone that sent both was signed out by its own duplicate.
    """
    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, settings)
    both_read = asyncio.Barrier(2)

    async def lookup(*_args):
        await both_read.wait()
        return user

    with patch("app.modules.account.tokens.users_repo.get_by_id", side_effect=lookup):
        results = await asyncio.wait_for(
            asyncio.gather(
                tokens.refresh_token_pair(fake_redis, refresh, AsyncMock(), settings),
                tokens.refresh_token_pair(fake_redis, refresh, AsyncMock(), settings),
                return_exceptions=True,
            ),
            timeout=2,
        )
    assert all(isinstance(result, tuple) for result in results), results
    successors = {result[1] for result in results if isinstance(result, tuple)}
    assert len(successors) == 1
    assert await _live_sessions(fake_redis, user.id) == successors
    for result in results:
        assert isinstance(result, tuple)
        assert await tokens.verify_access_token(fake_redis, result[0], settings) == user.id
    assert await fake_redis.get(f"revoked_since:{user.id}") is None


@pytest.mark.asyncio
async def test_a_refresh_whose_answer_was_lost_is_answered_again_within_the_grace(fake_redis):
    """The rotation committed but its answer never reached the phone (an app reload, a
    deadline, a dropped connection), so the phone presents the same token again. Seconds
    later that is the same phone, not a thief: it gets the successor, and stays signed in.
    (2026-11-02: a reload dropped the answer, the retry 7 s later was taken for reuse and
    every session of the account was revoked.)"""
    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, settings)
    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)):
        _lost_access, successor, _ = await tokens.refresh_token_pair(
            fake_redis, refresh, AsyncMock(), settings
        )
        access, again, user_out = await tokens.refresh_token_pair(
            fake_redis, refresh, AsyncMock(), settings
        )
        assert again == successor
        assert user_out.id == user.id
        assert await tokens.verify_access_token(fake_redis, access, settings) == user.id
        assert await _live_sessions(fake_redis, user.id) == {successor}
        # The successor is an ordinary live token: it rotates as usual.
        _, third, _ = await tokens.refresh_token_pair(fake_redis, successor, AsyncMock(), settings)
    assert await _live_sessions(fake_redis, user.id) == {third}
    assert await fake_redis.get(f"revoked_since:{user.id}") is None


@pytest.mark.asyncio
async def test_the_grace_lasts_seconds_and_a_later_replay_is_still_reuse(fake_redis):
    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, settings)
    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)):
        await tokens.refresh_token_pair(fake_redis, refresh, AsyncMock(), settings)
        ttl = await fake_redis.ttl(f"refresh_grace:{refresh}")
        assert 0 < ttl <= tokens.ROTATION_GRACE_SECONDS <= 10
        await fake_redis.delete(f"refresh_grace:{refresh}")  # the grace ran out
        with pytest.raises(AuthenticationError):
            await tokens.refresh_token_pair(fake_redis, refresh, AsyncMock(), settings)
    assert await _live_sessions(fake_redis, user.id) == set()
    assert await fake_redis.get(f"revoked_since:{user.id}") is not None


@pytest.mark.asyncio
async def test_a_replay_within_the_grace_after_sign_out_fails_and_spares_other_devices(fake_redis):
    """Within the grace a rotated-out token is a duplicate, never theft: once its successor
    has ended (signed out), it is refused, and the account's other devices stay signed in."""
    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, phone = await tokens.issue_token_pair(fake_redis, user.id, settings)
    _, tablet = await tokens.issue_token_pair(fake_redis, user.id, settings)
    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)):
        _, successor, _ = await tokens.refresh_token_pair(fake_redis, phone, AsyncMock(), settings)
        await tokens.revoke_refresh_token(fake_redis, successor)
        with pytest.raises(AuthenticationError):
            await tokens.refresh_token_pair(fake_redis, phone, AsyncMock(), settings)
    assert await _live_sessions(fake_redis, user.id) == {tablet}
    assert await fake_redis.get(f"revoked_since:{user.id}") is None


@pytest.mark.asyncio
async def test_purge_includes_session_issued_during_live_set_snapshot(fake_redis):
    from redis.asyncio.client import Pipeline

    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, first = await tokens.issue_token_pair(fake_redis, user.id, settings)
    smembers = Pipeline.smembers
    added = []

    async def snapshot_then_issue(pipe, key):
        snapshot = await smembers(pipe, key)
        if not added:
            _, refresh = await tokens.issue_token_pair(fake_redis, user.id, settings)
            added.append(refresh)
        return snapshot

    with patch("redis.asyncio.client.Pipeline.smembers", snapshot_then_issue):
        await tokens.purge_user_sessions(fake_redis, user.id, settings)

    assert await fake_redis.get(f"refresh:{first}") is None
    assert await fake_redis.get(f"refresh:{added[0]}") is None
    assert await fake_redis.smembers(f"refresh_user:{user.id}") == set()


@pytest.mark.asyncio
async def test_issue_failure_does_not_leave_untracked_refresh_token(fake_redis):
    settings = Settings(jwt_secret="x" * 32)
    with (
        patch(
            "redis.asyncio.client.Pipeline.execute",
            AsyncMock(side_effect=RedisConnectionError("connection unavailable")),
        ),
        pytest.raises(RedisUnavailableError),
    ):
        await tokens.issue_token_pair(fake_redis, api_user().id, settings)
    assert await fake_redis.keys("refresh:*") == []
    assert await fake_redis.keys("refresh_user:*") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("purge", [False, True], ids=["logout", "account-purge"])
async def test_repeated_transaction_conflicts_fail_retryably_without_hanging(fake_redis, purge):
    from redis.exceptions import WatchError

    user = api_user()
    settings = Settings(jwt_secret="x" * 32)
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, settings)
    with (
        patch(
            "redis.asyncio.client.Pipeline.execute",
            AsyncMock(side_effect=WatchError("connection lost while watching")),
        ),
        pytest.raises(RedisUnavailableError),
    ):
        if purge:
            await tokens.purge_user_sessions(fake_redis, user.id, settings)
        else:
            await tokens.revoke_refresh_token(fake_redis, refresh)
    raw = await fake_redis.get(f"refresh:{refresh}")
    assert isinstance(raw, bytes | str)
    assert _refresh_user_id(raw, refresh) == str(user.id)


@pytest.mark.asyncio
async def test_session_purge_redis_outage_is_retryable(fake_redis):
    with (
        patch(
            "redis.asyncio.client.Pipeline.execute",
            AsyncMock(side_effect=RedisConnectionError("connection unavailable")),
        ),
        pytest.raises(RedisUnavailableError),
    ):
        await tokens.purge_user_sessions(fake_redis, api_user().id, Settings(jwt_secret="x" * 32))
