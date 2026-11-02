"""Tests for app.repositories.usage with mocked AsyncSession."""

from datetime import date
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# A fixed day: the date only passes through to the fakes.
_DAY = date(2026, 10, 16)


@pytest.mark.asyncio
async def test_get_for_date_returns_usage(fake_session):
    """get_for_date should return the usage record from session.get."""
    from app.repositories.usage import get_for_date

    user_id = uuid4()
    today = _DAY
    mock_usage = MagicMock()
    fake_session.get.return_value = mock_usage

    result = await get_for_date(fake_session, user_id, today)

    assert result is mock_usage
    fake_session.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_tokens_uses_on_conflict_upsert(fake_session):
    """add_tokens must INSERT … ON CONFLICT DO UPDATE, not read-modify-write, and read
    the totals back from RETURNING rather than a second SELECT."""
    from app.repositories.usage import DayTotals, add_tokens

    fake_session.execute.return_value = MagicMock(**{"one.return_value": (100, 200)})

    result = await add_tokens(
        fake_session,
        uuid4(),
        _DAY,
        input_tokens=100,
        output_tokens=200,
        est_cost_usd=0.0125,
    )

    fake_session.execute.assert_awaited_once()
    statement = str(fake_session.execute.await_args.args[0])
    assert "ON CONFLICT" in statement and "RETURNING" in statement
    fake_session.get.assert_not_called()
    fake_session.add.assert_not_called()
    fake_session.commit.assert_awaited()
    assert result == DayTotals(100, 200)


@pytest.mark.asyncio
async def test_add_tokens_flush_without_commit(fake_session):
    from app.repositories.usage import add_tokens

    fake_session.execute.return_value = MagicMock(**{"one.return_value": (1, 2)})

    await add_tokens(fake_session, uuid4(), _DAY, input_tokens=1, output_tokens=2, commit=False)

    fake_session.flush.assert_awaited_once()
    fake_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_get_total_for_date_returns_sum(fake_session):
    """get_total_for_date should return input + output tokens."""
    from app.repositories.usage import get_total_for_date

    mock_usage = MagicMock()
    mock_usage.input_tokens = 400
    mock_usage.output_tokens = 300
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_usage
    fake_session.execute.return_value = mock_result

    result = await get_total_for_date(fake_session, uuid4(), _DAY)

    assert result == 700


@pytest.mark.asyncio
async def test_get_total_for_date_returns_zero_when_none(fake_session):
    """get_total_for_date should return 0 when no usage record exists."""
    from app.repositories.usage import get_total_for_date

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    fake_session.execute.return_value = mock_result

    result = await get_total_for_date(fake_session, uuid4(), _DAY)

    assert result == 0
