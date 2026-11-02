"""Refresh must survive transient failures and respect concurrent logout."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

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


@pytest.mark.asyncio
async def test_concurrent_refresh_has_one_winner_and_detects_replay(fake_redis):
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
    assert sum(isinstance(result, tuple) for result in results) == 1
    assert sum(isinstance(result, AuthenticationError) for result in results) == 1
    assert await fake_redis.smembers(f"refresh_user:{user.id}") == set()


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
