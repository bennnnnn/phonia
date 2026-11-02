"""Simple dated To-do repeats — daily / weekdays / weekly / monthly."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypeGuard
from zoneinfo import ZoneInfo

RecurrenceRule = Literal["daily", "weekdays", "weekly", "monthly"]
RECURRENCE_RULES: tuple[RecurrenceRule, ...] = (
    "daily",
    "weekdays",
    "weekly",
    "monthly",
)


def is_recurrence_rule(value: object) -> TypeGuard[RecurrenceRule]:
    return value in RECURRENCE_RULES


def _zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _as_local(dt: datetime, tz_name: str | None) -> datetime:
    tz = _zone(tz_name)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _add_month(local: datetime) -> datetime:
    month = local.month + 1
    year = local.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(local.day, monthrange(year, month)[1])
    return local.replace(year=year, month=month, day=day)


def _step_local(local: datetime, rule: RecurrenceRule) -> datetime:
    if rule == "daily":
        return local + timedelta(days=1)
    if rule == "weekly":
        return local + timedelta(days=7)
    if rule == "monthly":
        return _add_month(local)
    nxt = local + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def snap_first_due(
    due_at: datetime, rule: RecurrenceRule | None, *, timezone: str | None
) -> datetime:
    """Weekday repeats skip Sat/Sun for the first fire."""
    if rule != "weekdays":
        return due_at
    local = _as_local(due_at, timezone)
    while local.weekday() >= 5:
        local += timedelta(days=1)
    return local.astimezone(due_at.tzinfo or _zone(timezone))


def next_recurring_due(
    due_at: datetime,
    rule: RecurrenceRule,
    *,
    now: datetime,
    timezone: str | None,
) -> datetime:
    """Advance *due_at* until it is strictly after *now* in the user's timezone."""
    local = _as_local(due_at, timezone)
    now_local = _as_local(now, timezone)
    if local.astimezone(UTC) > now_local.astimezone(UTC):
        return due_at
    elapsed_days = max(0, (now_local.date() - local.date()).days)
    if rule == "monthly":
        months = max(0, (now_local.year - local.year) * 12 + now_local.month - local.month)
        # Preserve existing sequential month-end clamping, including skipped
        # Februarys, without walking every missed occurrence. Every 48-month
        # interval includes a non-leap February (the shortest possible month).
        day = local.day
        for offset in range(1, min(months, 48) + 1):
            index = local.year * 12 + local.month - 1 + offset
            day = min(day, monthrange(index // 12, index % 12 + 1)[1])
        index = local.year * 12 + local.month - 1 + months
        nxt = local.replace(year=index // 12, month=index % 12 + 1, day=day)
    else:
        days = elapsed_days // 7 * 7 if rule == "weekly" else elapsed_days
        nxt = local + timedelta(days=days)
        if rule == "weekdays":
            while nxt.weekday() >= 5:
                nxt += timedelta(days=1)
    if nxt.astimezone(UTC) <= now_local.astimezone(UTC):
        nxt = _step_local(nxt, rule)
    return nxt.astimezone(due_at.tzinfo or _zone(timezone))


def completed_fields(
    fields: Mapping[str, Any],
    *,
    due_at: datetime | None,
    rule: object,
    timezone: str | None,
    now: datetime,
) -> dict[str, Any]:
    """A write's fields, where ticking a repeating to-do finishes this occurrence only.

    Ticking "gym, every Monday" checked the row for good and ended the series. It now
    stays open, due at the next occurrence after this one (or after now, when several
    passed). Any other change passes through as it is.
    """
    if fields.get("checked") is not True or due_at is None or not is_recurrence_rule(rule):
        return dict(fields)
    changed = {key: value for key, value in fields.items() if key != "checked"}
    changed["due_at"] = next_recurring_due(due_at, rule, now=max(now, due_at), timezone=timezone)
    return changed
