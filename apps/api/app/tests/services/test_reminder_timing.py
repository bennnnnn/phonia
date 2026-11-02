from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.reminder_timing import (
    DEFAULT_REMINDER_LEAD_MINUTES,
    OVERDUE_MAX_HOURS,
    QuietHours,
    in_quiet_hours,
    reminder_at,
    reminder_title,
    resolve_reminder_lead_minutes,
)
from app.tests.fakes import make_user


def test_resolve_reminder_lead_minutes():
    assert resolve_reminder_lead_minutes(5) == 5
    assert resolve_reminder_lead_minutes(30) == 30
    assert resolve_reminder_lead_minutes(60) == 60
    assert resolve_reminder_lead_minutes(99) == DEFAULT_REMINDER_LEAD_MINUTES
    assert resolve_reminder_lead_minutes(None) == DEFAULT_REMINDER_LEAD_MINUTES


_DUE = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
_LONG_BEFORE = _DUE - timedelta(days=1)


@pytest.mark.parametrize("lead", [5, 10, 15, 30, 60])
def test_reminder_at_is_the_lead_time_before_it_is_due(lead: int) -> None:
    at = reminder_at(_DUE, set_at=_LONG_BEFORE, lead_minutes=lead, quiet=None)
    assert at == _DUE - timedelta(minutes=lead)


def test_reminder_at_an_unknown_lead_is_the_default() -> None:
    at = reminder_at(_DUE, set_at=None, lead_minutes=99, quiet=None)
    assert at == _DUE - timedelta(minutes=DEFAULT_REMINDER_LEAD_MINUTES)


@pytest.mark.parametrize(
    "set_offset_min, expected_offset_min",
    [
        # Set long before: the lead time applies.
        (-120, -10),
        (-10, -10),
        # Set 3 minutes before it is due, lead 10: not at once, but when due.
        (-3, 0),
        (0, 0),
        # Set after its time (already overdue): when it was set, never before.
        (5, 5),
    ],
)
def test_a_reminder_set_inside_its_lead_window_goes_out_when_due(
    set_offset_min: int, expected_offset_min: int
) -> None:
    set_at = _DUE + timedelta(minutes=set_offset_min)
    at = reminder_at(_DUE, set_at=set_at, lead_minutes=10, quiet=None)
    assert at == _DUE + timedelta(minutes=expected_offset_min)


def test_reminder_at_is_none_once_it_is_too_late_to_send() -> None:
    set_at = _DUE + timedelta(hours=OVERDUE_MAX_HOURS, minutes=1)
    assert reminder_at(_DUE, set_at=set_at, lead_minutes=10, quiet=None) is None


def test_reminder_at_reads_a_naive_time_as_utc() -> None:
    naive = _DUE.replace(tzinfo=None)
    assert reminder_at(naive, set_at=None, lead_minutes=10, quiet=None) == _DUE - timedelta(
        minutes=10
    )


def test_reminder_at_the_lead_time_is_elapsed_time_across_a_clock_change() -> None:
    """Ten minutes before 03:05 EDT on 8 March 2026 is 01:55 EST, not a 02:55 that never was."""
    due = datetime(2026, 3, 8, 3, 5, tzinfo=ZoneInfo("America/New_York"))
    at = reminder_at(due, set_at=None, lead_minutes=10, quiet=None)
    assert at == datetime(2026, 3, 8, 6, 55, tzinfo=UTC)


def _quiet(start: str = "22:00", end: str = "07:00", tz: str = "UTC") -> QuietHours:
    quiet = QuietHours.of(
        make_user(
            quiet_hours_enabled=True,
            quiet_hours_start_minute=_minute(start),
            quiet_hours_end_minute=_minute(end),
            timezone=tz,
        )
    )
    assert quiet is not None
    return quiet


def _minute(clock: str) -> int:
    hours, minutes = clock.split(":")
    return int(hours) * 60 + int(minutes)


Clock = tuple[int, int, int, int, int]


def _local(tz: str, clock: Clock, fold: int = 0) -> datetime:
    year, month, day, hour, minute = clock
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz), fold=fold)


def _utc(clock: Clock) -> datetime:
    return _local("UTC", clock)


@pytest.mark.parametrize(
    "due, lead, expected",
    [
        # The measured case: due 23:30, lead 10. Not 23:20 (the phone) but 07:00.
        ((2026, 1, 2, 23, 30), 10, (2026, 1, 3, 7, 0)),
        # Its lead time is before the window, its due time inside: the lead time holds.
        ((2026, 1, 2, 22, 5), 10, (2026, 1, 2, 21, 55)),
        ((2026, 1, 2, 22, 15), 10, (2026, 1, 3, 7, 0)),
        # After midnight, the same night's end.
        ((2026, 1, 3, 6, 55), 10, (2026, 1, 3, 7, 0)),
        ((2026, 1, 3, 7, 5), 10, (2026, 1, 3, 7, 0)),
        # The end itself is outside the window.
        ((2026, 1, 3, 8, 0), 60, (2026, 1, 3, 7, 0)),
        ((2026, 1, 2, 21, 55), 10, (2026, 1, 2, 21, 45)),
    ],
)
def test_reminder_at_waits_out_quiet_hours_across_midnight(
    due: Clock, lead: int, expected: Clock
) -> None:
    at = reminder_at(_utc(due), set_at=None, lead_minutes=lead, quiet=_quiet())
    assert at == _utc(expected)


def test_reminder_at_waits_out_a_daytime_window() -> None:
    quiet = _quiet("13:00", "15:00")
    due = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
    assert reminder_at(due, set_at=None, lead_minutes=10, quiet=quiet) == datetime(
        2026, 1, 2, 15, 0, tzinfo=UTC
    )


def test_reminder_at_a_reminder_set_during_quiet_hours_after_its_time_waits_for_morning() -> None:
    due = datetime(2026, 1, 2, 21, 0, tzinfo=UTC)
    set_at = datetime(2026, 1, 2, 23, 0, tzinfo=UTC)
    assert reminder_at(due, set_at=set_at, lead_minutes=10, quiet=_quiet()) == datetime(
        2026, 1, 3, 7, 0, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "tz, due, expected_utc",
    [
        # 07:00 on the user's clock, whatever their zone.
        ("Asia/Tokyo", (2026, 1, 2, 23, 30), (2026, 1, 2, 22, 0)),
        ("America/Los_Angeles", (2026, 1, 2, 23, 30), (2026, 1, 3, 15, 0)),
        ("Asia/Kolkata", (2026, 1, 2, 23, 30), (2026, 1, 3, 1, 30)),
        ("Australia/Sydney", (2026, 1, 2, 23, 30), (2026, 1, 2, 20, 0)),
        # A bad zone name reads as UTC.
        ("Not/AZone", (2026, 1, 2, 23, 30), (2026, 1, 3, 7, 0)),
    ],
)
def test_reminder_at_quiet_hours_are_on_the_users_clock(
    tz: str, due: Clock, expected_utc: Clock
) -> None:
    zone = tz if tz != "Not/AZone" else "UTC"
    at = reminder_at(_local(zone, due), set_at=None, lead_minutes=10, quiet=_quiet(tz=tz))
    assert at == _utc(expected_utc)


@pytest.mark.parametrize(
    "tz, due, expected_utc",
    [
        # Clocks spring forward overnight: 07:00 EDT is 11:00 UTC, not 12:00.
        ("America/New_York", (2026, 3, 7, 23, 30), (2026, 3, 8, 11, 0)),
        # And fall back: 07:00 EST is 12:00 UTC.
        ("America/New_York", (2026, 10, 31, 23, 30), (2026, 11, 1, 12, 0)),
        ("Europe/London", (2026, 3, 28, 23, 30), (2026, 3, 29, 6, 0)),
        ("Europe/London", (2026, 10, 24, 23, 30), (2026, 10, 25, 7, 0)),
    ],
)
def test_reminder_at_quiet_hours_end_on_the_wall_clock_across_dst(
    tz: str, due: Clock, expected_utc: Clock
) -> None:
    at = reminder_at(_local(tz, due), set_at=None, lead_minutes=10, quiet=_quiet(tz=tz))
    assert at == _utc(expected_utc)


def test_quiet_hours_ending_in_the_skipped_hour_end_at_the_jump() -> None:
    """New York skips 02:00-03:00 on 8 March 2026: a window to 02:30 ends at 03:00 EDT."""
    tz = "America/New_York"
    quiet = _quiet("22:00", "02:30", tz)
    end = quiet.end_after(_local(tz, (2026, 3, 7, 23, 20)))
    assert end == datetime(2026, 3, 8, 7, 0, tzinfo=UTC)
    assert quiet.contains(end - timedelta(minutes=1))
    assert not quiet.contains(end)


def test_quiet_hours_ending_in_the_repeated_hour_end_at_each_pass() -> None:
    """New York repeats 01:00-02:00 on 1 November 2026: 01:30 comes twice."""
    tz = "America/New_York"
    quiet = _quiet("22:00", "01:30", tz)
    first = quiet.end_after(_local(tz, (2026, 10, 31, 23, 20)))
    assert first == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    # The minute-of-day rule is quiet again once the clock reads 01:00 a second time.
    second = quiet.end_after(_local(tz, (2026, 11, 1, 1, 10), fold=1))
    assert second == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


def test_falling_back_to_before_the_window_ends_it_at_the_change() -> None:
    """London repeats 01:00-02:00 on 25 October 2026: a window from 01:30 to 03:20 is left
    when 02:00 BST becomes 01:00 GMT, not at 03:20."""
    tz = "Europe/London"
    quiet = _quiet("01:30", "03:20", tz)
    end = quiet.end_after(_local(tz, (2026, 10, 25, 1, 35)))
    assert end == datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    assert not quiet.contains(end)


def test_a_day_whose_free_minutes_are_skipped_waits_for_the_next_one() -> None:
    """Chile springs from 00:00 to 01:00 on 6 September 2026: a window from 00:30 to 00:00
    leaves no free minute that day, so it ends at midnight on the 7th."""
    tz = "America/Santiago"
    quiet = _quiet("00:30", "00:00", tz)
    end = quiet.end_after(_local(tz, (2026, 9, 5, 18, 0)))
    assert end == _local(tz, (2026, 9, 7, 0, 0))
    assert not quiet.contains(end)


_ZONES = [
    "UTC",
    "America/New_York",
    "Europe/London",
    "Australia/Lord_Howe",
    "Asia/Kathmandu",
    "America/Santiago",
    "Pacific/Chatham",
]


@settings(max_examples=300, deadline=None)
@given(
    due_minutes=st.integers(min_value=0, max_value=366 * 24 * 60),
    lead=st.sampled_from([5, 10, 15, 30, 60]),
    start=st.integers(min_value=0, max_value=1439),
    end=st.integers(min_value=0, max_value=1439),
    tz=st.sampled_from(_ZONES),
)
def test_reminder_at_is_the_first_moment_outside_quiet_hours(
    due_minutes: int, lead: int, start: int, end: int, tz: str
) -> None:
    """Never inside the window, never early, and no quiet-free minute skipped before it."""
    due = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=due_minutes)
    user = make_user(
        quiet_hours_enabled=True,
        quiet_hours_start_minute=start,
        quiet_hours_end_minute=end,
        timezone=tz,
    )
    quiet = QuietHours.of(user)
    at = reminder_at(due, set_at=None, lead_minutes=lead, quiet=quiet)
    base = due - timedelta(minutes=lead)
    assert at is not None and at >= base
    assert not in_quiet_hours(user, now=at)
    moment = base
    while moment < at:
        assert in_quiet_hours(user, now=moment)
        moment += timedelta(minutes=1)


def test_reminder_title_localizes_and_distinguishes_overdue():
    """Shared by both push and email so they can't drift apart on this — see
    the BUG FIX comment above _REMINDER_TITLES."""
    assert reminder_title(is_overdue=False, locale="en") == "Reminder"
    assert reminder_title(is_overdue=True, locale="en") == "Overdue reminder"
    assert reminder_title(is_overdue=False, locale="es") == "Recordatorio"
    assert reminder_title(is_overdue=True, locale="es") == "Recordatorio atrasado"
    # Unsupported/unset locale falls back to English rather than crashing.
    assert reminder_title(is_overdue=False, locale=None) == "Reminder"
    assert reminder_title(is_overdue=False, locale="am") == "Reminder"


def _quiet_user(*, enabled: bool = True, start: int = 1320, end: int = 420, tz: str = "UTC"):
    user = MagicMock()
    user.quiet_hours_enabled = enabled
    user.quiet_hours_start_minute = start
    user.quiet_hours_end_minute = end
    user.timezone = tz
    return user


def test_in_quiet_hours_off_is_never_quiet():
    assert in_quiet_hours(make_user()) is False
    assert (
        in_quiet_hours(_quiet_user(enabled=False), now=datetime(2026, 1, 2, 23, 0, tzinfo=UTC))
        is False
    )


def test_in_quiet_hours_wraps_midnight():
    user = _quiet_user()
    assert in_quiet_hours(user, now=datetime(2026, 1, 2, 22, 0, tzinfo=UTC)) is True
    assert in_quiet_hours(user, now=datetime(2026, 1, 2, 23, 30, tzinfo=UTC)) is True
    assert in_quiet_hours(user, now=datetime(2026, 1, 2, 6, 59, tzinfo=UTC)) is True
    assert in_quiet_hours(user, now=datetime(2026, 1, 2, 7, 0, tzinfo=UTC)) is False
    assert in_quiet_hours(user, now=datetime(2026, 1, 2, 12, 0, tzinfo=UTC)) is False


def test_in_quiet_hours_same_start_and_end_is_never_quiet():
    user = _quiet_user(start=600, end=600)
    assert in_quiet_hours(user, now=datetime(2026, 1, 2, 10, 0, tzinfo=UTC)) is False


def test_in_quiet_hours_same_day_window():
    user = _quiet_user(start=540, end=720)
    assert in_quiet_hours(user, now=datetime(2026, 1, 2, 9, 0, tzinfo=UTC)) is True
    assert in_quiet_hours(user, now=datetime(2026, 1, 2, 12, 0, tzinfo=UTC)) is False
    assert in_quiet_hours(user, now=datetime(2026, 1, 2, 8, 59, tzinfo=UTC)) is False
