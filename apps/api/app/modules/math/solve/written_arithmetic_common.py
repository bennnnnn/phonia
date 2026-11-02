"""Bounded exact-number helpers shared by written arithmetic algorithms."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

MAX_DIGITS = 12
MAX_DIVISION_DIGITS = 64
MAX_DECIMAL_PLACES = 6
WHOLE_PLACES = ("ones", "tens", "hundreds", "thousands", "ten-thousands")
DECIMAL_PLACES = ("tenths", "hundredths", "thousandths", "ten-thousandths")


def place_name(position: int, scale: int) -> str:
    power = position - scale
    if power >= 0:
        return WHOLE_PLACES[power] if power < len(WHOLE_PLACES) else f"10^{power} place"
    decimal_index = -power - 1
    return (
        DECIMAL_PLACES[decimal_index]
        if decimal_index < len(DECIMAL_PLACES)
        else f"10^{power} place"
    )


def number_parts(token: str, *, max_digits: int = MAX_DIGITS) -> tuple[Decimal, int] | None:
    raw = token.replace(",", "")
    if not raw or raw.startswith(("+", "-")):
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    digits = raw.replace(".", "").lstrip("0") or "0"
    scale = len(raw.partition(".")[2]) if "." in raw else 0
    if len(digits) > max_digits or scale > MAX_DECIMAL_PLACES:
        return None
    return value, scale


def scaled_number_parts(token: str, *, max_digits: int = MAX_DIGITS) -> tuple[int, int] | None:
    """Parse a non-negative plain decimal into an exact coefficient and scale."""
    raw = token.replace(",", "")
    if not raw or raw.startswith(("+", "-")):
        return None
    whole, point, fraction = raw.partition(".")
    if point and (not fraction or "." in fraction):
        return None
    if (whole and not whole.isdigit()) or (fraction and not fraction.isdigit()):
        return None
    if not whole and not fraction:
        return None
    digits = f"{whole or '0'}{fraction}"
    significant = digits.lstrip("0") or "0"
    scale = len(fraction)
    if len(significant) > max_digits or scale > MAX_DECIMAL_PLACES:
        return None
    return int(digits), scale


def scaled_integer(value: Decimal, scale: int) -> int:
    return int(value.scaleb(scale).to_integral_exact())


def format_scaled(value: int, scale: int) -> str:
    if scale == 0:
        return str(value)
    sign = "-" if value < 0 else ""
    digits = str(abs(value)).zfill(scale + 1)
    return f"{sign}{digits[:-scale]}.{digits[-scale:]}"
