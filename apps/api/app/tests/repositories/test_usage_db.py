"""Real-Postgres tests for app.repositories.usage.

`test_usage.py` mocks `session.get`/`session.execute`, so it can prove the
Python arithmetic in `add_tokens` (`existing + delta`) but not that the
composite-key upsert (`user_id`, `date`) actually round-trips through
Postgres correctly — e.g. a bug that queried/keyed on the wrong column
combination would still pass a mocked test since the mock ignores what key
was actually used. These tests call the repository through the `db_session`
fixture and re-verify totals with a fresh `SELECT` (`get_total_for_date`)
scoped by both user and date.
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.repositories import usage as usage_repo
from app.repositories import users as users_repo


async def _make_user(session):
    return await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


@pytest.mark.asyncio
async def test_add_tokens_accumulates_across_multiple_calls(db_session):
    """Two add_tokens calls for the same user/day must sum, proving this is
    a real upsert-then-increment rather than a last-write-wins overwrite."""
    user = await _make_user(db_session)
    today = date(2026, 7, 11)

    first = await usage_repo.add_tokens(
        db_session, user.id, today, input_tokens=100, output_tokens=50
    )
    assert first == (100, 50)

    second = await usage_repo.add_tokens(
        db_session, user.id, today, input_tokens=30, output_tokens=20
    )
    assert second == (130, 70)

    # Independent fresh SELECT (not just the in-memory object mutated above)
    # confirming the accumulated total actually persisted.
    total = await usage_repo.get_total_for_date(db_session, user.id, today)
    assert total == 200


@pytest.mark.asyncio
async def test_get_total_for_date_scoped_by_user_and_date(db_session):
    """A row for a different user, or the same user on a different day, must
    not bleed into the total for (user, day)."""
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    day = date(2026, 7, 11)
    other_day = day - timedelta(days=1)

    await usage_repo.add_tokens(db_session, user_a.id, day, input_tokens=100, output_tokens=100)
    await usage_repo.add_tokens(db_session, user_b.id, day, input_tokens=1000, output_tokens=1000)
    await usage_repo.add_tokens(
        db_session, user_a.id, other_day, input_tokens=5000, output_tokens=5000
    )

    assert await usage_repo.get_total_for_date(db_session, user_a.id, day) == 200
    assert await usage_repo.get_total_for_date(db_session, user_b.id, day) == 2000
    assert await usage_repo.get_total_for_date(db_session, user_a.id, other_day) == 10000
