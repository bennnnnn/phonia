"""How a money reply writes its numbers: sums, percents and dates."""

from __future__ import annotations

from datetime import date


def money_text(value: float) -> str:
    """``300000`` → ``300,000``; ``964.918`` → ``964.92``."""
    rounded = round(value, 2)
    return f"{rounded:,.0f}" if rounded == int(rounded) else f"{rounded:,.2f}"


def percent_text(value: float) -> str:
    """``6.270`` → ``6.27%``; ``1.0`` → ``1%``."""
    return f"{round(value, 3):g}%"


def day_text(day: date) -> str:
    """``2026-10-16`` → ``Oct 16, 2026``."""
    return f"{day:%b} {day.day}, {day.year}"
