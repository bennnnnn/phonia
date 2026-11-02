from datetime import datetime
from zoneinfo import ZoneInfo

from app.modules.todos.recurrence import next_recurring_due, snap_first_due


def test_next_daily_skips_to_future_morning() -> None:
    due = datetime(2026, 8, 20, 8, 0, tzinfo=ZoneInfo("America/New_York"))
    now = datetime(2026, 8, 22, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    nxt = next_recurring_due(due, "daily", now=now, timezone="America/New_York")
    local = nxt.astimezone(ZoneInfo("America/New_York"))
    assert local.day == 23
    assert local.hour == 8


def test_weekdays_skips_weekend() -> None:
    friday = datetime(2026, 8, 21, 8, 0, tzinfo=ZoneInfo("UTC"))
    saturday = datetime(2026, 8, 22, 9, 0, tzinfo=ZoneInfo("UTC"))
    nxt = next_recurring_due(friday, "weekdays", now=saturday, timezone="UTC")
    assert nxt.weekday() == 0


def test_snap_first_due_skips_saturday() -> None:
    saturday = datetime(2026, 8, 22, 8, 0, tzinfo=ZoneInfo("UTC"))
    snapped = snap_first_due(saturday, "weekdays", timezone="UTC")
    assert snapped.weekday() == 0


def test_daily_catches_up_years_in_one_call():
    due = datetime(2024, 1, 1, 8, tzinfo=ZoneInfo("UTC"))
    now = datetime(2026, 9, 4, 9, tzinfo=ZoneInfo("UTC"))
    assert next_recurring_due(due, "daily", now=now, timezone="UTC") == datetime(
        2026, 9, 5, 8, tzinfo=ZoneInfo("UTC")
    )


def test_fall_back_compares_instants_instead_of_repeated_clock_hour():
    zone = ZoneInfo("America/New_York")
    due = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    now = datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1)
    assert next_recurring_due(due, "daily", now=now, timezone=zone.key) == datetime(
        2026, 11, 2, 1, 30, tzinfo=zone
    )


def test_daily_repeat_preserves_wall_time_across_spring_dst():
    zone = ZoneInfo("America/New_York")
    due = datetime(2026, 3, 7, 8, tzinfo=zone)
    now = datetime(2026, 3, 7, 9, tzinfo=zone)
    nxt = next_recurring_due(due, "daily", now=now, timezone=zone.key)
    assert nxt == datetime(2026, 3, 8, 8, tzinfo=zone)
    assert nxt.utcoffset() != due.utcoffset()


def test_long_catchup_preserves_existing_repeat_rules_with_bounded_steps():
    from datetime import UTC
    from unittest.mock import patch

    from app.modules.todos import recurrence

    due = datetime(1990, 1, 31, 8, tzinfo=ZoneInfo("UTC"))
    now = datetime(2100, 9, 4, 9, tzinfo=ZoneInfo("UTC"))
    for rule in recurrence.RECURRENCE_RULES:
        expected = due
        while expected.astimezone(UTC) <= now.astimezone(UTC):
            expected = recurrence._step_local(expected, rule)
        with patch.object(recurrence, "_step_local", wraps=recurrence._step_local) as step:
            actual = next_recurring_due(due, rule, now=now, timezone="UTC")
        assert actual == expected
        assert step.call_count <= 1
