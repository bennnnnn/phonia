"""When a to-do's reminder goes out: one instant for push, email and the phone's own alert.

The phone scheduled its local alerts from its own copy of the lead rule and knew nothing of
quiet hours: with quiet hours 22:00–07:00, a to-do due at 23:30 alerted on the device at 23:20
while push waited until 07:00. The server now works out the instant (``reminder_at``) and
sends it with each to-do as ``notify_at``; the push and email schedulers send at it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.orm import User
from app.services import time_context as time_context_service
from app.services.locale import normalize_locale_code

DEFAULT_REMINDER_LEAD_MINUTES = 10
MAX_REMINDER_LEAD_MINUTES = 60
VALID_REMINDER_LEAD_MINUTES = frozenset({5, 10, 15, 30, 60})
OVERDUE_MAX_HOURS = 48
_MINUTES_PER_DAY = 1440
_MINUTE = timedelta(minutes=1)
_MAX_EXIT_STEPS = 4


def resolve_reminder_lead_minutes(raw: int | None) -> int:
    if raw in VALID_REMINDER_LEAD_MINUTES:
        return raw
    return DEFAULT_REMINDER_LEAD_MINUTES


def _utc(instant: datetime) -> datetime:
    """In UTC, where adding minutes is elapsed time (on a zone's clock it is wall time); a
    naive time is read as UTC."""
    return instant.astimezone(UTC) if instant.tzinfo is not None else instant.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class QuietHours:
    """A daily window on the user's clock when no reminder goes out; it may wrap midnight."""

    start_minute: int
    end_minute: int
    zone: ZoneInfo

    @classmethod
    def of(cls, user: User) -> QuietHours | None:
        """The user's window, or None when it is off. A zero-length window is never quiet."""
        if not user.quiet_hours_enabled:
            return None
        start, end = user.quiet_hours_start_minute, user.quiet_hours_end_minute
        if start == end or not (0 <= start < _MINUTES_PER_DAY and 0 <= end < _MINUTES_PER_DAY):
            return None
        return cls(start, end, time_context_service.resolve_timezone(user.timezone))

    def contains(self, instant: datetime) -> bool:
        local = _utc(instant).astimezone(self.zone)
        minute = local.hour * 60 + local.minute
        if self.start_minute < self.end_minute:
            return self.start_minute <= minute < self.end_minute
        return minute >= self.start_minute or minute < self.end_minute

    def end_after(self, instant: datetime) -> datetime:
        """``instant``, or the first moment after it outside the window when it falls inside.

        The window is on the wall clock, so a DST change moves its end in UTC, and a jump
        of the clock can leave it early: springing forward past its end, or falling back
        to before its start.
        """
        instant = _utc(instant)
        # Each step reaches the window's end or a clock change before it; a change inside
        # the window, or a day whose free minutes the clocks skip, takes another.
        for _ in range(_MAX_EXIT_STEPS):
            if not self.contains(instant):
                return instant
            end = self._next_wall_end(instant)
            jump = _next_offset_change(self.zone, instant, end)
            instant = jump if jump is not None else end
        return instant

    def _next_wall_end(self, instant: datetime) -> datetime:
        """The first time after ``instant`` the clock reads the window's end."""
        local_day = instant.astimezone(self.zone).date()
        end = time(self.end_minute // 60, self.end_minute % 60)
        found: list[datetime] = []
        for days in range(3):
            wall = datetime.combine(local_day + timedelta(days=days), end)
            # Both passes of a repeated hour; a skipped one reads back as another time.
            for fold in (0, 1):
                moment = wall.replace(tzinfo=self.zone, fold=fold).astimezone(UTC)
                if moment > instant and moment.astimezone(self.zone).replace(tzinfo=None) == wall:
                    found.append(moment)
        return min(found)


def _next_offset_change(zone: ZoneInfo, start: datetime, end: datetime) -> datetime | None:
    """The first whole minute in ``(start, end]`` on another UTC offset than ``start``."""
    offset = start.astimezone(zone).utcoffset()
    base = start.replace(second=0, microsecond=0)
    steps = -(-(end - base) // _MINUTE)
    if (base + steps * _MINUTE).astimezone(zone).utcoffset() == offset:
        return None
    low, high = 0, steps
    while high - low > 1:
        middle = (low + high) // 2
        if (base + middle * _MINUTE).astimezone(zone).utcoffset() == offset:
            low = middle
        else:
            high = middle
    return base + high * _MINUTE


def reminder_at(
    due_at: datetime,
    *,
    set_at: datetime | None,
    lead_minutes: int | None,
    quiet: QuietHours | None,
) -> datetime | None:
    """When the reminder for a to-do due at ``due_at`` goes out; None when it never does.

    The lead time before it is due. One set inside its own lead window ("remind me in 3
    minutes", lead 10) goes out when it is due, not the moment it is saved, and one set
    after its due time goes out when it was set. ``set_at`` is when its due time was set
    (``todo_items.due_set_at``): no other edit moves the instant.
    An instant inside quiet hours waits for their end; 48 hours past due nothing goes out.
    """
    due = _utc(due_at)
    at = due - timedelta(minutes=resolve_reminder_lead_minutes(lead_minutes))
    if set_at is not None and _utc(set_at) > at:
        at = max(due, _utc(set_at))
    if quiet is not None:
        at = quiet.end_after(at)
    return at if at <= due + timedelta(hours=OVERDUE_MAX_HOURS) else None


def in_quiet_hours(user: User, now: datetime | None = None) -> bool:
    """True when the user has quiet hours on and ``now`` is inside the window."""
    quiet = QuietHours.of(user)
    return quiet is not None and quiet.contains(now or datetime.now(UTC))


# Push and email title a reminder from this one table (modules/notifications/push.py
# and reminder_email.py), in the user's language, so the two channels cannot drift.
_REMINDER_TITLES: dict[str, dict[str, str]] = {
    "en": {"reminder": "Reminder", "overdue": "Overdue reminder"},
    "es": {"reminder": "Recordatorio", "overdue": "Recordatorio atrasado"},
    "fr": {"reminder": "Rappel", "overdue": "Rappel en retard"},
    "de": {"reminder": "Erinnerung", "overdue": "Überfällige Erinnerung"},
    "it": {"reminder": "Promemoria", "overdue": "Promemoria in ritardo"},
    "pt": {"reminder": "Lembrete", "overdue": "Lembrete atrasado"},
    "ru": {"reminder": "Напоминание", "overdue": "Просроченное напоминание"},
    "tr": {"reminder": "Hatırlatma", "overdue": "Gecikmiş hatırlatma"},
}


def reminder_title(*, is_overdue: bool, locale: str | None) -> str:
    code = normalize_locale_code(locale)
    bundle = _REMINDER_TITLES.get(code, _REMINDER_TITLES["en"])
    return bundle["overdue"] if is_overdue else bundle["reminder"]
